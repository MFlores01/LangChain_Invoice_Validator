import tempfile, os

def save_temp_file(uploaded_file, suffix):
    """Save an uploaded file to a temporary file and return its path."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        return tmp_file.name
    
def remove_temp_file(file_path):
    if os.path.exists(file_path):
        os.unlink(file_path)