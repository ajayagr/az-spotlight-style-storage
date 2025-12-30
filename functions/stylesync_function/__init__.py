"""
StyleSync Azure Function
HTTP-Triggered function to process images with AI style transfer.
"""
import azure.functions as func
import json
import logging
import os
from azure.storage.blob import BlobServiceClient

# Import StyleSync core logic
from .stylesync.sync import map_expected_state, get_missing_files
from .stylesync.clients import get_generator, GeneratorResult
from .stylesync.storage.blob import AzureBlobStorageProvider

logger = logging.getLogger(__name__)

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP Trigger handler for StyleSync.
    
    Expected JSON body:
    {
        "source_container": "source-images",
        "source_path": "originals/",
        "output_container": "styled-images",
        "output_path": "processed/",
        "styles": [
            {"index": 1, "name": "Watercolor", "prompt_text": "...", "strength": 0.7},
            ...
        ]
    }
    """
    logger.info("StyleSync function triggered.")
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json"
        )
    
    # Extract parameters
    source_container = req_body.get("source_container", "file-container")
    source_path = req_body.get("source_path", "")
    output_container = req_body.get("output_container", source_container)
    output_path = req_body.get("output_path", "styled/")
    styles = req_body.get("styles", [])
    provider_name = req_body.get("provider", "azure")
    
    if not styles:
        return func.HttpResponse(
            json.dumps({"error": "No styles provided"}),
            status_code=400,
            mimetype="application/json"
        )
    
    # Initialize Storage
    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        return func.HttpResponse(
            json.dumps({"error": "AZURE_STORAGE_CONNECTION_STRING not configured"}),
            status_code=500,
            mimetype="application/json"
        )
    
    source_provider = AzureBlobStorageProvider(connection_string, source_container)
    output_provider = AzureBlobStorageProvider(connection_string, output_container)
    
    # Initialize Generator (Azure OpenAI)
    try:
        generator = get_generator(provider_name)
    except ValueError as e:
        return func.HttpResponse(
            json.dumps({"error": f"Generator error: {e}"}),
            status_code=500,
            mimetype="application/json"
        )
    
    # Process
    results = {
        "status": "completed",
        "source": f"{source_container}/{source_path}",
        "output": f"{output_container}/{output_path}",
        "processed": [],
        "failed": [],
        "skipped": []
    }
    
    try:
        # Map Expected State
        expected_state = map_expected_state(source_provider, source_path, styles)
        
        # Get Missing Files
        tasks = get_missing_files(output_provider, expected_state, output_path)
        
        logger.info(f"Expected: {len(expected_state)}, Tasks: {len(tasks)}")
        
        for task in tasks:
            source_item = task['source_item']
            style = task['style']
            output_filename = task['output_filename']
            
            try:
                # Read Source
                input_data = source_provider.read_file(source_item.path)
                
                # Generate Styled Image
                result: GeneratorResult = generator.process_image_bytes(
                    input_data,
                    source_item.name,
                    style['prompt_text'],
                    style['strength']
                )
                
                if result and result.data:
                    # Write to Output
                    target_path = f"{output_path.rstrip('/')}/{output_filename}"
                    output_provider.write_file(target_path, result.data)
                    results["processed"].append(output_filename)
                else:
                    results["failed"].append(output_filename)
                    
            except Exception as e:
                logger.error(f"Error processing {output_filename}: {e}")
                results["failed"].append(output_filename)
        
        # Files already existing
        results["skipped"] = [k for k in expected_state.keys() if k not in [t['output_filename'] for t in tasks]]
        
    except Exception as e:
        logger.error(f"Critical error: {e}")
        results["status"] = "failed"
        results["error"] = str(e)
    
    return func.HttpResponse(
        json.dumps(results, indent=2),
        status_code=200 if results["status"] == "completed" else 500,
        mimetype="application/json"
    )
