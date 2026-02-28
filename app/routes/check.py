import os
import logging
from dotenv import load_dotenv
load_dotenv()
print("DEBUG KEY:", os.getenv("GEMINI_API_KEY"))  # temporary debug

def _model():
    """Return a configured Gemini GenerativeModel, or raise RuntimeError."""
    try:
        import google.generativeai as genai  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError('google-generativeai package not installed') from exc

    api_key = os.getenv('GEMINI_API_KEY')
    print("DEBUG KEY INSIDE FUNCTION:", api_key)  # temporary debug
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY environment variable is not set')

    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.5-flash')

from flask import Blueprint, request, jsonify



_model()