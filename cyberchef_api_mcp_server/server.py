#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import httpx
import logging
from typing import Optional
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP
from cyberchef_api_mcp_server.cyberchefoperations import CyberChefOperations

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Create an MCP server
mcp = FastMCP("CyberChef API MCP Server")

# Determine the CyberChef API URL
cyberchef_api_url = os.getenv("CYBERCHEF_API_URL")
if cyberchef_api_url is None:
    log.warning("There is no environment variable CYBERCHEF_API_URL defaulting to http://localhost:3000/")
    cyberchef_api_url = "http://localhost:3000/"


class CyberChefRecipeOperation(BaseModel):
    """Model for a recipe operation with or without arguments"""
    op: str
    args: Optional[list] = None


def convert_recipe_to_api_format(recipe: list[CyberChefRecipeOperation]) -> list:
    """
    Convert CyberChefRecipeOperation objects to the format expected by the CyberChef API
    
    The API supports multiple formats:
    - Simple operation name as string: "To Hex"
    - Operation with args object: {"op": "To Hex", "args": {"delimiter": "Colon"}}
    - Operation with args array: {"op": "To Morse Code", "args": ["Dash/Dot", "Backslash", "Comma"]}
    - Array of operation names: ["to decimal", "MD5", "to braille"]
    
    :param recipe: list of CyberChefRecipeOperation objects
    :return: recipe in API format
    """
    if not recipe:
        return []
    
    # If all operations have no args, return simple operation names
    if all(not op.args or len(op.args) == 0 for op in recipe):
        return [op.op for op in recipe]
    
    # Convert to API format with proper args handling
    api_recipe = []
    for op in recipe:
        op_dict = {"op": op.op}
        
        # Only include args if they exist and are not empty
        if op.args and len(op.args) > 0:
            # Check if args look like they should be positional (simple values)
            # or named (dicts or complex objects)
            if len(op.args) == 1 and not isinstance(op.args[0], (dict, list)):
                # Single simple argument, could be positional or named
                # We'll try positional first (array format)
                op_dict["args"] = op.args
            else:
                # Multiple arguments or complex argument - use as positional array
                op_dict["args"] = op.args
        
        api_recipe.append(op_dict)
    
    return api_recipe


def create_api_request(endpoint: str, request_data: dict) -> dict:
    """
    Send a POST request to one of the CyberChef API endpoints to process request data and retrieve the response

    :param endpoint: API endpoint to retrieve data from
    :param request_data: data to send with the POST request
    :return: dict object of response data
    """
    api_url = f"{cyberchef_api_url}{endpoint}"
    request_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:
        log.info(f"Attempting to send POST request to {api_url}")
        log.info(f"Request data: {request_data}")
        response = httpx.post(
            url=api_url,
            headers=request_headers,
            json=request_data,
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as http_exc:
        log.error(f"HTTP error {http_exc.response.status_code} during POST request to {api_url} - {http_exc}")
        try:
            error_data = http_exc.response.json()
            return {"error": f"HTTP {http_exc.response.status_code}: {error_data.get('message', str(http_exc))}"}
        except:
            return {"error": f"HTTP {http_exc.response.status_code}: {str(http_exc)}"}
    except httpx.RequestError as req_exc:
        log.error(f"Exception raised during HTTP POST request to {api_url} - {req_exc}")
        return {"error": f"Exception raised during HTTP POST request to {api_url} - {req_exc}"}


@mcp.resource("data://cyberchef-operations-categories")
def get_cyberchef_operations_categories() -> list:
    """Get updated Cyber Chef categories for additional context / selection of the correct operations"""
    cyberchef_ops = CyberChefOperations()
    return cyberchef_ops.get_all_categories()


@mcp.resource("data://cyberchef-operations-by-category/{category}")
def get_cyberchef_operation_by_category(category: str) -> list:
    """
    Get list of Cyber Chef operations for a selected category

    :param category: cyber chef category to get operations for
    :return:
    """
    cyberchef_ops = CyberChefOperations()
    return cyberchef_ops.get_operations_by_category(category=category)


@mcp.tool()
def bake_recipe(input_data: str, recipe: list[CyberChefRecipeOperation]) -> dict:
    """
    Bake (execute) a recipe (a list of operations) in order to derive an outcome from the input data

    :param input_data: the data in which to perform the recipe operation(s) on
    :param recipe: a pydantic model of operations to 'bake'/execute on the input data
    :return:
    """
    # Convert recipe to API format
    api_recipe = convert_recipe_to_api_format(recipe)
    
    request_data = {
        "input": input_data,
        "recipe": api_recipe
    }
    log.info(f"Sending bake request with recipe: {api_recipe}")
    response_data = create_api_request(endpoint="bake", request_data=request_data)

    # If the response has a byte array, decode and return
    data_type = response_data.get("type")
    if data_type is not None and data_type == "byteArray":
        try:
            decoded_value = bytes(response_data["value"]).decode()
            response_data["value"] = decoded_value
            response_data["type"] = "string"
        except (ValueError, TypeError) as e:
            log.warning(f"Could not decode byte array: {e}")
            
    return response_data


@mcp.tool()
def batch_bake_recipe(batch_input_data: list[str], recipe: list[CyberChefRecipeOperation]) -> dict:
    """
    Bake (execute) a recipe (a list of operations) in order to derive an outcome from a batch of input data

    :param batch_input_data: the batch of data in which to perform the recipe operation(s) on
    :param recipe: a list of operations to 'bake'/execute on the input data
    :return:
    """
    # Convert recipe to API format
    api_recipe = convert_recipe_to_api_format(recipe)
    
    request_data = {
        "input": batch_input_data,
        "recipe": api_recipe
    }
    log.info(f"Sending batch bake request with recipe: {api_recipe}")
    response_data = create_api_request(endpoint="batch/bake", request_data=request_data)

    # If any of the responses have a byte array, decode and return
    if isinstance(response_data, list):
        for response in response_data:
            data_type = response.get("type")
            if data_type is not None and data_type == "byteArray":
                try:
                    decoded_value = bytes(response["value"]).decode()
                    response["value"] = decoded_value
                    response["type"] = "string"
                except (ValueError, TypeError) as e:
                    log.warning(f"Could not decode byte array: {e}")

    return response_data


@mcp.tool()
def perform_magic_operation(
        input_data: str,
        depth: int = 3,
        intensive_mode: bool = False,
        extensive_language_support: bool = False,
        crib_str: str = ""
) -> dict:
    """
    CyberChef's magic operation is designed to automatically detect how your data is encoded and which operations can be
    used to decode it

    :param input_data: the data in which to perform the magic operation on
    :param depth: how many levels of recursion to attempt pattern matching and speculative execution on the input data
    :param intensive_mode: optional argument which will run additional operations and take considerably longer to run
    :param extensive_language_support: if this is true all 245 languages are supported opposed to the top 38 by default
    :param crib_str: argument for any known plaintext string or regex
    :return:
    """
    request_data = {
        "input": input_data,
        "args": {
            "depth": depth,
            "intensive_mode": intensive_mode,
            "extensive_language_support": extensive_language_support,
            "crib": crib_str
        }
    }
    return create_api_request(endpoint="magic", request_data=request_data)


def main():
    """Initialize and run the server"""
    log.info("Starting the CyberChef MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
