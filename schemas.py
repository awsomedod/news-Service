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