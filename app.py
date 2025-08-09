from flask import Flask, request, jsonify, g
from functools import wraps
from firebase_admin import credentials, firestore, initialize_app
import jwt
from jwt import ExpiredSignatureError, DecodeError, InvalidTokenError
from google.cloud import secretmanager
from flask_cors import CORS
import json

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

app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=True
)

def token_required(f):
    @wraps(f)
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
    return decorator





@app.route("/users/<user_id>")
@token_required
def get_user(user_id):
    if g.user['id'] != user_id:
        return jsonify({'message': 'Unauthorized'}), 401
    
    return jsonify({'user': g.user})

if __name__ == "__main__":
    app.run(debug=True)