import os
import uuid
from werkzeug.utils import secure_filename
from supabase_client import supabase
from flask import current_app
import mimetypes

class StorageManager:
    """Handles file uploads and retrievals using Supabase Storage"""
    
    BUCKET_NAME = "uploads"  # You'll need to create this bucket in Supabase
    
    @staticmethod
    def upload_file(file, job_id, subfolder=None):
        """
        Upload a file to Supabase Storage
        
        Args:
            file: Flask file object
            job_id: UUID of the job
            subfolder: Optional subfolder (e.g., 'accessories')
            
        Returns:
            str: File path in storage or None if failed
        """
        if not file or not file.filename:
            return None
            
        # Generate secure filename
        filename = secure_filename(file.filename)
        # Add timestamp to prevent conflicts
        timestamp = str(uuid.uuid4())[:8]
        name, ext = os.path.splitext(filename)
        unique_filename = f"{name}_{timestamp}{ext}"
        
        # Build storage path
        if subfolder:
            storage_path = f"{job_id}/{subfolder}/{unique_filename}"
        else:
            storage_path = f"{job_id}/{unique_filename}"
        
        try:
            # Read file content
            file_bytes = file.read()
            print(f"StorageManager: Attempting to upload {unique_filename} ({len(file_bytes)} bytes)")
            
            # Get MIME type
            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                mime_type = "application/octet-stream"
                
            print(f"StorageManager: MIME type: {mime_type}, Storage path: {storage_path}")
            
            print(f"📤 Uploading {storage_path} to bucket '{StorageManager.BUCKET_NAME}'")
            print(f"📄 File size: {len(file_bytes)} bytes, MIME type: {mime_type}")
            
            # Upload to Supabase Storage
            response = supabase.storage.from_(StorageManager.BUCKET_NAME).upload(
                path=storage_path,
                file=file_bytes,
                file_options={
                    "content-type": mime_type,
                    "upsert": "true"
                }
            )
            
            print(f"📊 Upload response: {response}")
            
            # Check response format - Supabase Python client returns different formats
            if isinstance(response, dict) and response.get('path'):
                print(f"✅ Upload successful: {response['path']}")
                return storage_path
            elif hasattr(response, 'path') and response.path:
                print(f"✅ Upload successful: {response.path}")
                return storage_path
            else:
                print(f"❌ Upload failed - unexpected response format: {type(response)}")
                print(f"Response content: {response}")
                return None
                
        except Exception as e:
            print(f"❌ Upload error: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def get_file_url(storage_path):
        """
        Get public URL for a file in Supabase Storage
        
        Args:
            storage_path: Path to file in storage
            
        Returns:
            str: Public URL or None if failed
        """
        try:
            print(f"🔗 Getting URL for: {storage_path}")
            
            # Get public URL from Supabase Storage
            result = supabase.storage.from_(StorageManager.BUCKET_NAME).get_public_url(storage_path)
            
            print(f"🔗 URL result: {result}")
            
            # The get_public_url method returns the URL directly as a string
            if isinstance(result, str) and result.startswith('http'):
                return result
            elif isinstance(result, dict) and result.get('publicUrl'):
                return result['publicUrl']
            else:
                print(f"❌ Unexpected URL format: {type(result)} - {result}")
                return None
                
        except Exception as e:
            print(f"❌ Error getting file URL: {e}")
            return None
    
    @staticmethod
    def list_files(job_id, subfolder=None):
        """
        List all files for a job
        
        Args:
            job_id: UUID of the job
            subfolder: Optional subfolder to filter by
            
        Returns:
            list: List of file paths
        """
        try:
            if subfolder:
                prefix = f"{job_id}/{subfolder}/"
            else:
                prefix = f"{job_id}/"
                
            result = supabase.storage.from_(StorageManager.BUCKET_NAME).list(prefix)
            
            if result:
                return [item['name'] for item in result if item['name'] != '.emptyFolderPlaceholder']
            return []
            
        except Exception as e:
            print(f"Error listing files: {e}")
            return []
    
    @staticmethod
    def delete_file(storage_path):
        """
        Delete a file from Supabase Storage
        
        Args:
            storage_path: Path to file in storage
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            result = supabase.storage.from_(StorageManager.BUCKET_NAME).remove([storage_path])
            return result.status_code == 200
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False
    
    @staticmethod
    def delete_job_files(job_id):
        """
        Delete all files for a job
        
        Args:
            job_id: UUID of the job
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # List all files for this job
            files = StorageManager.list_files(job_id)
            if not files:
                return True
                
            # Build full paths for deletion
            file_paths = [f"{job_id}/{file}" for file in files]
            
            # Delete all files
            result = supabase.storage.from_(StorageManager.BUCKET_NAME).remove(file_paths)
            return result.status_code == 200
            
        except Exception as e:
            print(f"Error deleting job files: {e}")
            return False

    @staticmethod
    def get_files_with_urls(job_id, subfolder=None):
        """
        Get all files for a job with their public URLs
        
        Args:
            job_id: UUID of the job
            subfolder: Optional subfolder to filter by
            
        Returns:
            list: List of dicts with 'name' and 'url' keys
        """
        files = StorageManager.list_files(job_id, subfolder)
        result = []
        
        for file in files:
            if subfolder:
                storage_path = f"{job_id}/{subfolder}/{file}"
            else:
                storage_path = f"{job_id}/{file}"
                
            url = StorageManager.get_file_url(storage_path)
            if url:
                result.append({
                    'name': file,
                    'url': url,
                    'storage_path': storage_path
                })
                
        return result