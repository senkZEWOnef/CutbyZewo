import os
import uuid
import shutil
from werkzeug.utils import secure_filename
from flask import current_app, url_for
import mimetypes

class LocalStorageManager:
    """Handles file uploads and retrievals using local file system"""
    
    BASE_UPLOAD_DIR = "static/uploads"
    
    @staticmethod
    def upload_file(file, job_id, subfolder=None):
        """
        Upload a file to local storage
        
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
            storage_dir = os.path.join(LocalStorageManager.BASE_UPLOAD_DIR, str(job_id), subfolder)
        else:
            storage_dir = os.path.join(LocalStorageManager.BASE_UPLOAD_DIR, str(job_id))
        
        # Ensure directory exists
        os.makedirs(storage_dir, exist_ok=True)
        
        file_path = os.path.join(storage_dir, unique_filename)
        
        try:
            # Save file to local storage
            file.save(file_path)
            print(f"✅ File uploaded to: {file_path}")
            
            # Return relative path for database storage
            if subfolder:
                return f"{job_id}/{subfolder}/{unique_filename}"
            else:
                return f"{job_id}/{unique_filename}"
                
        except Exception as e:
            print(f"❌ Upload error: {e}")
            return None
    
    @staticmethod
    def get_file_url(storage_path):
        """
        Get URL for a file in local storage
        
        Args:
            storage_path: Path to file in storage
            
        Returns:
            str: URL or None if failed
        """
        try:
            # Build full file path
            full_path = os.path.join(LocalStorageManager.BASE_UPLOAD_DIR, storage_path)
            
            # Check if file exists
            if os.path.exists(full_path):
                # Return URL that Flask can serve
                return f"/static/uploads/{storage_path}"
            else:
                print(f"❌ File not found: {full_path}")
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
            list: List of file names
        """
        try:
            if subfolder:
                search_dir = os.path.join(LocalStorageManager.BASE_UPLOAD_DIR, str(job_id), subfolder)
            else:
                search_dir = os.path.join(LocalStorageManager.BASE_UPLOAD_DIR, str(job_id))
            
            if not os.path.exists(search_dir):
                return []
                
            files = []
            for item in os.listdir(search_dir):
                item_path = os.path.join(search_dir, item)
                if os.path.isfile(item_path):
                    files.append(item)
            
            return files
            
        except Exception as e:
            print(f"Error listing files: {e}")
            return []
    
    @staticmethod
    def delete_file(storage_path):
        """
        Delete a file from local storage
        
        Args:
            storage_path: Path to file in storage
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            full_path = os.path.join(LocalStorageManager.BASE_UPLOAD_DIR, storage_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                print(f"✅ File deleted: {full_path}")
                return True
            return False
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
            job_dir = os.path.join(LocalStorageManager.BASE_UPLOAD_DIR, str(job_id))
            if os.path.exists(job_dir):
                shutil.rmtree(job_dir)
                print(f"✅ Job directory deleted: {job_dir}")
                return True
            return True  # Directory doesn't exist, so "success"
            
        except Exception as e:
            print(f"Error deleting job files: {e}")
            return False

    @staticmethod
    def get_files_with_urls(job_id, subfolder=None):
        """
        Get all files for a job with their URLs
        
        Args:
            job_id: UUID of the job
            subfolder: Optional subfolder to filter by
            
        Returns:
            list: List of dicts with 'name' and 'url' keys
        """
        files = LocalStorageManager.list_files(job_id, subfolder)
        result = []
        
        for file in files:
            if subfolder:
                storage_path = f"{job_id}/{subfolder}/{file}"
            else:
                storage_path = f"{job_id}/{file}"
                
            url = LocalStorageManager.get_file_url(storage_path)
            if url:
                result.append({
                    'name': file,
                    'url': url,
                    'storage_path': storage_path
                })
                
        return result