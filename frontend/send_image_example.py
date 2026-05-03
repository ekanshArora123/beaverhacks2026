"""
Example Python script showing how to send images to the frontend API endpoint.

This demonstrates how a Flask server (or any Python application) can upload
images to the Node.js/Express API.

Requirements:
    pip install requests

Usage:
    python send_image_example.py path/to/image.png
"""

import requests
import sys
import os


def upload_image(image_path, endpoint='http://localhost:3001/api/upload-image'):
    """
    Upload a single image to the API.
    
    Args:
        image_path: Path to the image file
        endpoint: API endpoint URL
    
    Returns:
        dict: Response from the server
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    with open(image_path, 'rb') as f:
        files = {'image': f}
        response = requests.post(endpoint, files=files)
    
    return response.json()


def update_example_image(image_path, slot='example1'):
    """
    Update one of the example image slots (example1 or example2).
    
    Args:
        image_path: Path to the image file
        slot: Which slot to update ('example1' or 'example2')
    
    Returns:
        dict: Response from the server
    """
    if slot not in ['example1', 'example2']:
        raise ValueError("Slot must be 'example1' or 'example2'")
    
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    endpoint = f'http://localhost:3001/api/update-image/{slot}'
    
    with open(image_path, 'rb') as f:
        files = {'image': f}
        response = requests.post(endpoint, files=files)
    
    return response.json()


def upload_multiple_images(image_paths):
    """
    Upload multiple images at once.
    
    Args:
        image_paths: List of paths to image files
    
    Returns:
        dict: Response from the server
    """
    files = []
    for path in image_paths:
        if not os.path.exists(path):
            print(f"Warning: Skipping {path} (not found)")
            continue
        files.append(('images', open(path, 'rb')))
    
    try:
        response = requests.post('http://localhost:3001/api/upload-images', files=files)
        return response.json()
    finally:
        # Close all file handles
        for _, f in files:
            f.close()


# Example Flask integration
def flask_example():
    """
    Example showing how to integrate with a Flask application.
    """
    from flask import Flask, request, jsonify
    import tempfile
    
    app = Flask(__name__)
    
    @app.route('/process-image', methods=['POST'])
    def process_image():
        """
        Flask endpoint that receives an image and forwards it to the frontend API.
        """
        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400
        
        file = request.files['image']
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        
        try:
            # Forward to frontend API
            result = upload_image(tmp_path)
            return jsonify(result)
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    return app


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python send_image_example.py <image_path> [slot]")
        print("\nExamples:")
        print("  python send_image_example.py image.png")
        print("  python send_image_example.py image.png example1")
        print("  python send_image_example.py image.png example2")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    try:
        if len(sys.argv) >= 3:
            # Update specific slot
            slot = sys.argv[2]
            print(f"Updating {slot} with {image_path}...")
            result = update_example_image(image_path, slot)
        else:
            # Upload to general uploads
            print(f"Uploading {image_path}...")
            result = upload_image(image_path)
        
        print("\nSuccess!")
        print(f"Response: {result}")
        
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
