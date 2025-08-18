from flask import Flask, request, jsonify, g, Response
from firebase_admin.firestore import transactional
from firebase_admin import credentials, firestore, initialize_app
import jwt
from jwt import ExpiredSignatureError, DecodeError, InvalidTokenError
from google.cloud import secretmanager
from flask_cors import CORS
import json
from agent import suggestNewsSources, generate_topics, generate_topic_summary
from openrouterClient import OpenRouterClient
import asyncio
from datetime import datetime, timezone


_client = secretmanager.SecretManagerServiceClient()
_project_id = "news-467923" # or hard‐code your project test

def get_secret(secret_id: str, version: str = "latest") -> str:
    name = f"projects/{_project_id}/secrets/{secret_id}/versions/{version}"
    response = _client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")

JWT_SECRET = get_secret("JWT_SECRET")

firebase_cred_json = get_secret("firebaseCredentials")
firebase_cred = json.loads(firebase_cred_json)

cred = credentials.Certificate(firebase_cred)
initialize_app(cred)
db = firestore.client()
transaction = db.transaction()

llm_client = OpenRouterClient("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", "google/gemini-flash-1.5-8b")

app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=True
)

def token_required(f):
    def decorator(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]

        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            # Decode the token
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            # Find the user, assuming user_id is in the token
            user_id = data["sub"]
            user_ref = db.collection('users').document(user_id)
            user_doc = user_ref.get()
            if not user_doc.exists:
                return jsonify({'message': 'User not found'}), 404
            g.user = user_doc.to_dict()
            g.user['id'] = user_id
        except ExpiredSignatureError:
            # Specifically catch the expired token
            return jsonify({'message': 'Token has expired'}), 401
        except (DecodeError, InvalidTokenError):
            # Catch any other token decoding issues
            return jsonify({'message': 'Token is invalid'}), 401
        except Exception as e:
            # General exception catch
            return jsonify({'message': str(e)}), 500

        return f(*args, **kwargs)
    decorator.__name__ = f.__name__
    return decorator





@app.route("/user")
@token_required
def get_user():
    return jsonify({'user': g.user})

@app.route("/health")
def index():
    return "Hello, World!"

# Option 1: Using asyncio.run() (Simple but creates new event loop each time)
@app.route("/suggest-sources", methods=["POST"])
@token_required
def suggest_sources():
    """Suggest news sources for a given topic using asyncio.run()"""
    try:
        data = request.get_json()
        topic = data.get('topic')
        
        if not topic:
            return jsonify({'error': 'Topic is required'}), 400
        
        # This creates a new event loop for each request - not optimal for production
        sources = asyncio.run(suggestNewsSources(topic, llm_client))
        
        return jsonify({
            'topic': topic,
            'sources': sources,
            'count': len(sources)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@transactional
def update_news(txn, user_id, summaries):
    user_ref = db.collection('users').document(user_id)
    txn.update(user_ref, {'summary_runs': firestore.ArrayUnion([{
        'date_and_time': datetime.now(timezone.utc),
        'summaries': summaries
    }])})
    return user_id

# Option 3: Advanced news processing endpoint
@app.route("/generate-news", methods=["POST"])
@token_required
def generate_news():
    """Generate categorized news summaries from sources"""
    try:
        data = request.get_json()
        sources = data.get('sources', [])
        
        if not sources:
            return jsonify({'error': 'Sources array is required'}), 400
        app.logger.info(f"Generating news for sources: {sources}")
        summaries = asyncio.run(provideNews_advanced(sources, llm_client))
        
        update_news(transaction, g.user['id'], summaries)

        return jsonify({
            'summaries': summaries,
            'date_and_time': datetime.now(timezone.utc)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# @app.route("/generate-news-stream", methods=["POST"])
# @token_required
# def generate_news_stream():
#     """Stream news summaries as they're generated"""
#     try:
#         data = request.get_json()
#         sources = data.get('sources', [])
        
#         def generate_summaries():
#             # First generate topics to get the correct count
#             topics = generate_topics(sources, llm_client)
            
#             # Now send start message with correct topic count
            
#             summaries = []
#             for i, topic in enumerate(topics):
#                 # Generate single summary
#                 summary = asyncio.run(generate_topic_summary(topic, llm_client))
#                 summaries.append(summary)
                
#                 # Stream immediately with correct totals
#                 yield f"data: {json.dumps({
#                     'type': 'summary',
#                     'summary': summary,
#                     'index': i,
#                     'completed': i + 1,
#                     'total': len(topics)  # Fixed: use len(topics) instead of len(sources)
#                 })}\n\n"
            
#             # Save to database
#             update_news(transaction, g.user['id'], summaries)
            
#             # Complete
#             yield f"data: {json.dumps({'type': 'complete'})}\n\n"
        
#         return Response(generate_summaries(), mimetype='text/event-stream', headers={
#             'Cache-Control': 'no-cache',
#             'Connection': 'keep-alive',
#             'Access-Control-Allow-Origin': '*',
#             'Access-Control-Allow-Headers': 'Content-Type,Authorization'
#         })
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

@transactional
def update_sources(txn, user_id, sources):
    user_ref = db.collection('users').document(user_id)
    
    txn.update(user_ref, {'sources': sources})
        
    return user_id

@app.route("/update-sources", methods=["POST"])
@token_required
def update_sources_sync():
    data = request.get_json()
    user_id = g.user['id']
    sources = data.get('sources', [])
    
    # Validate sources format
    if not isinstance(sources, list):
        return jsonify({'error': 'Sources must be an array'}), 400
    
    # Create filtered sources with only required fields
    filtered_sources = []
    required_fields = ['description', 'name', 'url']
    
    for i, source in enumerate(sources):
        if not isinstance(source, dict):
            return jsonify({'error': f'Source at index {i} must be an object'}), 400
        
        for field in required_fields:
            if field not in source:
                return jsonify({'error': f'Source at index {i} is missing required field: {field}'}), 400
            if not isinstance(source[field], str):
                return jsonify({'error': f'Source at index {i} field "{field}" must be a string'}), 400
            if not source[field].strip():
                return jsonify({'error': f'Source at index {i} field "{field}" cannot be empty'}), 400
        
        # Create filtered source with only the required fields
        filtered_source = {field: source[field] for field in required_fields}
        
        filtered_sources.append(filtered_source)
    # Filter out duplicate URLs
    seen_urls = set()
    unique_sources = []
    
    for source in filtered_sources:
        if source['url'] not in seen_urls:
            seen_urls.add(source['url'])
            unique_sources.append(source)
    
    filtered_sources = unique_sources
    update_sources(transaction, user_id, filtered_sources)
    return jsonify({'new_sources': filtered_sources}), 200

if __name__ == "__main__":
    app.run(debug=True)