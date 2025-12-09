from openrouterClient import OpenRouterClient
from schemas import sources_schema, categorization_response_schema, news_summary_response_schema
import requests
import time
import asyncio
import aiohttp
import math
from webReader import fetch_webpage_python
import random
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from webReader import fetch_webpage_python
import json

@dataclass
class Topic:
    """Data class to represent a news topic with its sources."""
    name: str
    sources: List[str]

def estimateTokenCount(text: str):
    # Method 1: Character-based estimation (1 token ≈ 4 characters)
    charBasedEstimate = math.ceil(len(text) / 4)

    # Method 2: Word-based estimation (1 token ≈ 0.75 words)
    wordCount = len(text.split())
    wordBasedEstimate = math.ceil(wordCount / 0.75)

    # Return the average of both methods for better accuracy
    return (charBasedEstimate + wordBasedEstimate) // 2



def create_categorization_prompt(persistent_memory: List[Topic], content: str) -> str:
    """Create a prompt for categorizing news content into topics.
    
    Args:
        persistent_memory: List of existing topics
        content: The news content to categorize
        
    Returns:
        Formatted prompt string for the LLM
    """
    existing_topics = (
        f"\n\nCurrent topics:\n{chr(10).join([topic.name for topic in persistent_memory])}"
        if persistent_memory
        else "\n\nNo existing topics yet."
    )

    prompt = f"""You are a news categorization expert. You will be given a single news article and a list of existing topics.

Here is the content to categorize:
{content}

=========================

Here is the list of existing topics:
{existing_topics}

First, analyze if this content is about technical issues, webpage loading errors, API responses, HTML issues or other non-newsworthy technical content. If it is, return {{"skip": true}}.

Otherwise, analyze the content and categorize it appropriately. You should return an array of topic assignments where each assignment contains:

1. **topicName**: The name of the topic (either an existing topic name or a new topic name you're creating)
2. **isNew**: A boolean indicating whether this is a new topic (true) or an existing topic (false)
3. **furtherReadings**: (optional) An array of URLs to complete articles related to this topic (if available in the content)

Guidelines:
- If the content fits an existing topic, use that topic's exact name and set isNew to false
- If the content doesn't fit any existing topics, you can create one or more new topic names and set isNew to true for each
- You can assign the content to multiple topics if it covers multiple subjects (including a mix of existing and new topics)
- Ensure topic names are clear, descriptive, and unique
- Use exact topic names from the existing list when categorizing into existing topics
- When creating new topics, ensure they are distinct and don't overlap with each other
- For each topic assignment, extract any relevant URLs from the content that link to complete articles about that topic
- The furtherReadings URLs should be direct links to full articles, not homepages or category pages
- Limit furtherReadings to a maximum of 3 URLs per topic assignment to ensure the most newsworthy and relevant links are prioritized
- Limit the total number of topic assignments to a maximum of 5 to ensure the most relevant topics are prioritized
- If no relevant article links are found for a topic, you can omit the furtherReadings field or set it to an empty array

Your response should be a JSON object with either:
1. {{"skip": true}} for technical/error content
2. {{"skip": false, "assignments": [...]}} for newsworthy content
"""
    return prompt

def create_summary_prompt(category: str, relevant_html_content: List[str]) -> str:
    """Create a prompt for generating news summaries.
    
    Args:
        category: The topic/category name
        relevant_html_content: List of HTML content from relevant sources
        
    Returns:
        Formatted prompt string for the LLM
    """
    indexed_sources = "\n\n------------\n\n".join([
        f"Source {index}:\n{content}"
        for index, content in enumerate(relevant_html_content)
    ])

    summary_length = '300'

    prompt = f"""You are a world-class news summarizer. You will be provided with a topic name and content from multiple news sources related to that topic.

Please provide a comprehensive summary of the news events for this topic. The summary should be detailed and {summary_length} words long.

Here is the content from the different news sources, separated by '------------':
{indexed_sources}

Your output should be a summary of the news articles in the following category: {category}. The summary should be detailed and {summary_length} words long.

Also, provide select a relevant image for the summary from the urls in the content. Also provide a title for the summary.

Your output should be a JSON object with the following fields:
- title: string
- summary: string
- image: string
"""
    return prompt


async def isValidUrl(source: str):
    """Asynchronously check if a URL is valid and accessible."""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(source, allow_redirects=True) as response:
                return response.status < 400
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return False


def createSuggestionPrompt(topic: str):
    return f"""You are a news expert. You will suggest news sources based on the topic.

    Topic: {topic}

    Suggest 5 valid URLs of news sources related to the topic."""

async def suggestNewsSources(topic : str, client: OpenRouterClient):
    """Suggest news sources for a topic and validate URLs asynchronously."""
    prompt = createSuggestionPrompt(topic)
    
    response = client.generateStructuredOutput(prompt, schema=sources_schema, online=True)
    
    # Validate URLs concurrently
    sources = response.get("sources", [])
    validation_tasks = [isValidUrl(source.get("url")) for source in sources]
    validation_results = await asyncio.gather(*validation_tasks)
    
    # Filter out invalid URLs
    validSources = [source for source, is_valid in zip(sources, validation_results) if is_valid]
    
    return validSources

def fetch_webpages(validatedSources: list[dict[str, str]]):
    source_urls = [source["url"] for source in validatedSources]
    webpages = [fetch_webpage_python(url) for url in source_urls]
    return webpages

async def provideNews_async(sources: list[dict[str, str]], client: OpenRouterClient) -> list[str]:
    """Asynchronously fetch webpages and generate news summaries concurrently.
    
    Args:
        sources: List of validated source dictionaries
        client: OpenRouter client for text generation
        
    Returns:
        List of news summaries
    """
    # Fetch all webpages concurrently
    webpages = fetch_webpages(sources)
    
    # Create tasks for generating summaries concurrently
    async def generate_summary(webpage: str) -> str:
        """Generate a news summary for a single webpage."""
        prompt = f"""You are a news expert. You will provide a news summary based on the following webpage:

        {webpage}

        Provide a news summary of the webpage. The summary should be 500 words or less.
        """
        # Note: client.generateText is synchronous, so we run it in a thread pool
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, client.generateText, prompt)
        return response
    
    # Generate all summaries concurrently
    summary_tasks = [generate_summary(webpage) for webpage in webpages]
    summaries = await asyncio.gather(*summary_tasks)
    
    # Print results
    for i, summary in enumerate(summaries):
        print(f"Summary {i+1}:")
        print(summary)
        print("-" * 50)
    
    return summaries

def generate_topics(sources: list[str], client: OpenRouterClient) -> List[Dict[str, Any]]:
    """Generate topics for a list of sources."""
    try:
        print('Starting provideNews_advanced function with sources:', sources)
        
        # Fetch HTML content from all provided sources concurrently
        html_content = [
            {"url": source, "content": fetch_webpage_python(source)}
            for source in sources
        ]
        
        print('Fetched HTML content from all sources')

        # Initialize persistent memory to track topics across content items
        persistent_memory: List[Topic] = []
        print('Initialized empty persistent_memory')

        # Process each content item and categorize it into topics (SYNCHRONOUSLY as requested)
        for content_item in html_content:
            print('Processing content from URL:', content_item["url"])
            
            prompt = create_categorization_prompt(persistent_memory, content_item["content"])
            print('Created categorization prompt')
            
            # Run categorization synchronously using thread pool
            categorization_response = client.generateStructuredOutput(prompt, categorization_response_schema)
            print('Received categorization response from LLM')

            # Skip processing if no valid assignments or if content should be skipped
            if (not categorization_response or 
                not categorization_response.get("assignments") or 
                len(categorization_response.get("assignments", [])) == 0 or 
                categorization_response.get("skip", False)):
                
                print('--------------------------------======================--------------------------------')
                print(categorization_response)
                print('No valid assignments received, skipping content item')
                print('Skipping content item:', content_item["url"])
                print('--------------------------------======================--------------------------------')
                continue

            # Filter out invalid URLs from further readings
            for assignment in categorization_response["assignments"]:
                if "furtherReadings" in assignment and assignment["furtherReadings"]:
                    assignment["furtherReadings"] = [
                        url for url in assignment["furtherReadings"] 
                        if isValidUrl(url)
                    ]
            print('Filtered invalid URLs from further readings')

            print('Processing assignments:', categorization_response["assignments"])

            # Process each topic assignment
            for assignment in categorization_response["assignments"]:
                topic_name = assignment["topicName"]
                is_new = assignment["isNew"]
                further_readings = assignment.get("furtherReadings", [])
                
                print('Processing assignment for topic:', topic_name)

                # Skip invalid topic names
                if not topic_name or topic_name.strip() == "":
                    print('Invalid topic name, skipping assignment')
                    continue

                # Find existing topic with case-insensitive matching
                topic = next((t for t in persistent_memory if t.name.lower() == topic_name.lower()), None)
                print('Found existing topic?', topic is not None)

                if is_new:
                    # Handle new topic creation
                    if topic:
                        print('LLM suggested new topic but found existing one with same name')
                        # LLM suggested creating a new topic, but one with the same name already exists.
                        # We'll treat this as adding to the existing topic.
                        if content_item["url"] not in topic.sources:
                            topic.sources.append(content_item["url"])
                            print('Added new source to existing topic')
                        else:
                            print('Source already exists in topic')
                        
                        # Add furtherReadings to existing topic if provided
                        if further_readings:
                            print('Processing further readings for existing topic')
                            for url in further_readings:
                                if url not in topic.sources:
                                    topic.sources.append(url)
                                    print('Added further reading URL to topic:', url)
                    else:
                        print('Creating new topic:', topic_name)
                        # Create new topic
                        sources_list = [content_item["url"]]
                        
                        # Add furtherReadings to new topic if provided
                        if further_readings:
                            print('Adding further readings to new topic')
                            sources_list.extend(further_readings)
                        
                        new_topic = Topic(name=topic_name, sources=sources_list)
                        persistent_memory.append(new_topic)
                        print('New topic created and added to persistent_memory')
                else:
                    # Handle existing topic assignment
                    if topic:
                        print('Adding to existing topic:', topic_name)
                        # Categorize into existing topic
                        if content_item["url"] not in topic.sources:
                            topic.sources.append(content_item["url"])
                            print('Added new source to topic')
                        
                        # Add furtherReadings to existing topic if provided
                        if further_readings:
                            print('Processing further readings for existing topic')
                            for url in further_readings:
                                if url not in topic.sources:
                                    topic.sources.append(url)
                                    print('Added further reading URL:', url)
                    else:
                        print('LLM indicated existing topic but not found, creating new:', topic_name)
                        # LLM said it's existing, but we couldn't find it.
                        # This could be an LLM error or a slight naming mismatch.
                        # Safest to create it as new.
                        sources_list = [content_item["url"]]
                        
                        # Add furtherReadings to new topic if provided
                        if further_readings:
                            print('Adding further readings to new topic')
                            sources_list.extend(further_readings)
                        
                        new_topic = Topic(name=topic_name, sources=sources_list)
                        persistent_memory.append(new_topic)
                        print('Created new topic due to missing reference')
            yield persistent_memory
    except Exception as error:
        print('Error generating news summary:', error)
        raise




        
async def generate_topic_summary(topic: Topic, client: OpenRouterClient) -> Dict[str, Any]:
    """Generate summary for a single topic."""
    print('Generating summary for topic:', topic.name)
    
    # Fetch HTML content for all sources in this topic
    relevant_html_content = [fetch_webpage_python(source) for source in topic.sources]
    print('Fetched HTML content for all sources in topic')
    
    summary_prompt = create_summary_prompt(topic.name, relevant_html_content)
    print('Created summary prompt')
    
    # Generate summary using thread pool (since client is synchronous)
    loop = asyncio.get_running_loop()
    summary_response = await loop.run_in_executor(
        None,
        client.generateStructuredOutput,
        summary_prompt,
        news_summary_response_schema
    )
    print('Received summary from LLM')
    

    
    print('--------------------------------')
    print(topic.name)
    print(topic.sources)
    print(summary_response.get("summary", "No summary"))
    print(summary_response.get("image", "No image"))
    
    return summary_response

async def provideNews_advanced(sources: list[str], client: OpenRouterClient) -> List[Dict[str, Any]]:
    """Advanced news processing with categorization and summary generation.
    
    Args:
        sources: List of URL strings to process
        client: OpenRouter client for LLM interactions
        
    Returns:
        List of news summary dictionaries with id, title, summary, and image
    """
    try:
        print('Starting provideNews_advanced function with sources:', sources)
        
        # Fetch HTML content from all provided sources concurrently
        html_content = [
            {"url": source, "content": fetch_webpage_python(source)}
            for source in sources
        ]
        
        print('Fetched HTML content from all sources')

        # Initialize persistent memory to track topics across content items
        persistent_memory: List[Topic] = []
        print('Initialized empty persistent_memory')

        # Process each content item and categorize it into topics (SYNCHRONOUSLY as requested)
        for content_item in html_content:
            print('Processing content from URL:', content_item["url"])
            
            prompt = create_categorization_prompt(persistent_memory, content_item["content"])
            print('Created categorization prompt')
            
            # Run categorization synchronously using thread pool
            categorization_response = client.generateStructuredOutput(prompt, categorization_response_schema)
            print('Received categorization response from LLM')

            # Skip processing if no valid assignments or if content should be skipped
            if (not categorization_response or 
                not categorization_response.get("assignments") or 
                len(categorization_response.get("assignments", [])) == 0 or 
                categorization_response.get("skip", False)):
                
                print('--------------------------------======================--------------------------------')
                print(categorization_response)
                print('No valid assignments received, skipping content item')
                print('Skipping content item:', content_item["url"])
                print('--------------------------------======================--------------------------------')
                continue

            # Filter out invalid URLs from further readings
            for assignment in categorization_response["assignments"]:
                if "furtherReadings" in assignment and assignment["furtherReadings"]:
                    assignment["furtherReadings"] = [
                        url for url in assignment["furtherReadings"] 
                        if isValidUrl(url)
                    ]
            print('Filtered invalid URLs from further readings')

            print('Processing assignments:', categorization_response["assignments"])

            # Process each topic assignment
            for assignment in categorization_response["assignments"]:
                topic_name = assignment["topicName"]
                is_new = assignment["isNew"]
                further_readings = assignment.get("furtherReadings", [])
                
                print('Processing assignment for topic:', topic_name)

                # Skip invalid topic names
                if not topic_name or topic_name.strip() == "":
                    print('Invalid topic name, skipping assignment')
                    continue

                # Find existing topic with case-insensitive matching
                topic = next((t for t in persistent_memory if t.name.lower() == topic_name.lower()), None)
                print('Found existing topic?', topic is not None)

                if is_new:
                    # Handle new topic creation
                    if topic:
                        print('LLM suggested new topic but found existing one with same name')
                        # LLM suggested creating a new topic, but one with the same name already exists.
                        # We'll treat this as adding to the existing topic.
                        if content_item["url"] not in topic.sources:
                            topic.sources.append(content_item["url"])
                            print('Added new source to existing topic')
                        else:
                            print('Source already exists in topic')
                        
                        # Add furtherReadings to existing topic if provided
                        if further_readings:
                            print('Processing further readings for existing topic')
                            for url in further_readings:
                                if url not in topic.sources:
                                    topic.sources.append(url)
                                    print('Added further reading URL to topic:', url)
                    else:
                        print('Creating new topic:', topic_name)
                        # Create new topic
                        sources_list = [content_item["url"]]
                        
                        # Add furtherReadings to new topic if provided
                        if further_readings:
                            print('Adding further readings to new topic')
                            sources_list.extend(further_readings)
                        
                        new_topic = Topic(name=topic_name, sources=sources_list)
                        persistent_memory.append(new_topic)
                        print('New topic created and added to persistent_memory')
                else:
                    # Handle existing topic assignment
                    if topic:
                        print('Adding to existing topic:', topic_name)
                        # Categorize into existing topic
                        if content_item["url"] not in topic.sources:
                            topic.sources.append(content_item["url"])
                            print('Added new source to topic')
                        
                        # Add furtherReadings to existing topic if provided
                        if further_readings:
                            print('Processing further readings for existing topic')
                            for url in further_readings:
                                if url not in topic.sources:
                                    topic.sources.append(url)
                                    print('Added further reading URL:', url)
                    else:
                        print('LLM indicated existing topic but not found, creating new:', topic_name)
                        # LLM said it's existing, but we couldn't find it.
                        # This could be an LLM error or a slight naming mismatch.
                        # Safest to create it as new.
                        sources_list = [content_item["url"]]
                        
                        # Add furtherReadings to new topic if provided
                        if further_readings:
                            print('Adding further readings to new topic')
                            sources_list.extend(further_readings)
                        
                        new_topic = Topic(name=topic_name, sources=sources_list)
                        persistent_memory.append(new_topic)
                        print('Created new topic due to missing reference')

        # Generate summaries for all topics asynchronously (as requested)
        news_summary_response_items = []
        print('Starting summary generation for all topics')
        
        async def generate_topic_summary(topic: Topic) -> Dict[str, Any]:
            """Generate summary for a single topic."""
            print('Generating summary for topic:', topic.name)
            
            # Fetch HTML content for all sources in this topic
            relevant_html_content = [fetch_webpage_python(source) for source in topic.sources]
            print('Fetched HTML content for all sources in topic')
            
            summary_prompt = create_summary_prompt(topic.name, relevant_html_content)
            print('Created summary prompt')
            
            # Generate summary using thread pool (since client is synchronous)
            loop = asyncio.get_running_loop()
            summary_response = await loop.run_in_executor(
                None,
                client.generateStructuredOutput,
                summary_prompt,
                news_summary_response_schema
            )
            print('Received summary from LLM')
            

            
            print('--------------------------------')
            print(topic.name)
            print(topic.sources)
            print(summary_response.get("summary", "No summary"))
            print(summary_response.get("image", "No image"))
            
            return summary_response
        
        # Generate all summaries concurrently
        if persistent_memory:
            summary_tasks = [generate_topic_summary(topic) for topic in persistent_memory]
            news_summary_response_items = await asyncio.gather(*summary_tasks)
        
        return news_summary_response_items
        
    except Exception as error:
        print('Error generating news summary:', error)
        raise


def sse_event(event: str, data: Any) -> str:
    """Format an SSE event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

def generate_news_streaming(sources: list[str], client: OpenRouterClient, db_updater):
    """
    Streaming generator for SSE.
    Steps:
        1. Categorize news → stream topics discovered
        2. Summarize topics → stream summaries one by one
    """
    try:
        yield sse_event("start", {"message": "Starting news generation..."})

        # -------------------------------------------------------------------
        # STEP 1 — CATEGORIZATION (stream topics as they are created)
        # -------------------------------------------------------------------

        persistent_memory: list[Topic] = []
        yield sse_event("status", {"message": "Categorizing sources..."})

        html_content = [
            {"url": src, "content": fetch_webpage_python(src)}
            for src in sources
        ]

        for idx, content_item in enumerate(html_content):

            prompt = create_categorization_prompt(persistent_memory, content_item["content"])
            categorization_response = client.generateStructuredOutput(prompt, categorization_response_schema)

            if (not categorization_response or 
                not categorization_response.get("assignments") or 
                categorization_response.get("skip", False)):
                continue

            # Process assignments
            for assignment in categorization_response["assignments"]:
                topic_name = assignment["topicName"]
                is_new = assignment["isNew"]
                further_readings = assignment.get("furtherReadings", [])

                if not topic_name:
                    continue

                topic = next((t for t in persistent_memory if t.name.lower() == topic_name.lower()), None)

                if is_new:
                    if topic:
                        # add source to existing topic
                        if content_item["url"] not in topic.sources:
                            topic.sources.append(content_item["url"])
                        for url in further_readings:
                            if url not in topic.sources and isValidUrl(url):
                                topic.sources.append(url)
                    else:
                        # create new topic
                        new_topic = Topic(name=topic_name, sources=[content_item["url"]])
                        for url in further_readings:
                            if isValidUrl(url):
                                new_topic.sources.append(url)

                        persistent_memory.append(new_topic)

                        # STREAM THE NEW TOPIC IMMEDIATELY
                        yield sse_event("topic", {
                            "topicName": new_topic.name,
                            "totalTopics": len(persistent_memory)
                        })

                else:
                    # existing topic case
                    if topic:
                        if content_item["url"] not in topic.sources:
                            topic.sources.append(content_item["url"])
                        for url in further_readings:
                            if url not in topic.sources and isValidUrl(url):
                                topic.sources.append(url)
                    else:
                        # create as new if missing
                        new_topic = Topic(name=topic_name, sources=[content_item["url"]])
                        for url in further_readings:
                            if isValidUrl(url):
                                new_topic.sources.append(url)

                        persistent_memory.append(new_topic)

                        yield sse_event("topic", {
                            "topicName": new_topic.name,
                            "totalTopics": len(persistent_memory)
                        })

        # -------------------------------------------------------------------
        # STEP 2 — SUMMARIZATION (stream each summary as soon as it's ready)
        # -------------------------------------------------------------------

        if not persistent_memory:
            yield sse_event("done", {"message": "No topics discovered."})
            return

        yield sse_event("status", {
            "message": "Generating summaries...",
            "topicCount": len(persistent_memory)
        })

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def summarize_topic(topic: Topic):
            html_list = [fetch_webpage_python(src) for src in topic.sources]
            summary_prompt = create_summary_prompt(topic.name, html_list)
            return await loop.run_in_executor(
                None,
                client.generateStructuredOutput,
                summary_prompt,
                news_summary_response_schema
            )

        tasks = [summarize_topic(topic) for topic in persistent_memory]
        db_summaries = ["" for topic in persistent_memory]
        
        # Asynchronously gather but stream as they finish
        for idx, coro in enumerate(asyncio.as_completed(tasks)):
            summary = loop.run_until_complete(coro)

            db_summaries[idx] = summary

            # STREAM EACH SUMMARY AS IT FINISHES
            yield sse_event("summary", {
                "index": idx,
                "topic": persistent_memory[idx].name,
                "summary": summary
            })

        db_updater(db_summaries)
        yield sse_event("done", {"message": "All summaries completed."})

    except Exception as e:
        yield sse_event("error", {"error": str(e)})