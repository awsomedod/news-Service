sources_schema = {
  "type": "json_schema",
  "json_schema": {
    "name": "sources",
    "strict": True,
    "schema": {
      "type": "object",
      "properties": {
        "sources": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {
                "type": "string",
                "description": "Name of the source"
              },
              "url": {
                "type": "string",
                "description": "URL of the source"
              },
              "description": {
                "type": "string",
                "description": "Short description of the source"
              }
            },
            "required": ["name", "url", "description"],
            "additionalProperties": False
          }
        }
      },
      "required": ["sources"],
      "additionalProperties": False
    }
  }
}

categorization_response_schema = {
  "type": "json_schema",
  "json_schema": {
    "name": "categorization_response",
    "strict": True,
    "schema": {
      "type": "object",
      "properties": {
        "skip": {
          "type": "boolean",
          "description": "Whether to skip processing this content item"
        },
        "assignments": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "topicName": {
                "type": "string",
                "description": "The name of the topic (either existing or new)"
              },
              "isNew": {
                "type": "boolean",
                "description": "Whether this is a new topic (true) or existing topic (false)"
              },
              "furtherReadings": {
                "type": "array",
                "items": {
                  "type": "string"
                },
                "description": "Array of URLs for further reading (max 3)",
                "maxItems": 3
              }
            },
            "required": ["topicName", "isNew"],
            "additionalProperties": False
          },
          "maxItems": 5,
          "description": "Array of topic assignments (max 5)"
        }
      },
      "required": ["assignments"],
      "additionalProperties": False
    }
  }
}

news_summary_response_schema = {
  "type": "json_schema",
  "json_schema": {
    "name": "news_summary_response",
    "strict": True,
    "schema": {
      "type": "object",
      "properties": {
        "title": {
          "type": "string",
          "description": "Title of the news story"
        },
        "summary": {
          "type": "string",
          "description": "Summary content of the news story"
        },
        "image": {
          "type": "string",
          "description": "URL or path to an image representing the news story"
        }
      },
      "required": ["title", "summary", "image"],
      "additionalProperties": False
    }
  }
}