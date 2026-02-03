import json
from typing import List, Dict, Any, Optional
from pathlib import Path
import urllib.request
import urllib.error
import urllib.parse


class APIError(Exception):
    """Exception raised for API-related errors."""
    pass


class APIClient:
    """Client for interacting with the config API."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize API client.
        
        Args:
            base_url: Base URL of the API server (default: http://localhost:8000)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = 10  # seconds
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make HTTP request to API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., "/api/configs")
            data: Optional JSON data for POST requests
            
        Returns:
            Response data as dictionary
            
        Raises:
            APIError: If request fails
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                req = urllib.request.Request(url, method="GET")
            elif method == "POST":
                json_data = json.dumps(data).encode('utf-8') if data else b'{}'
                req = urllib.request.Request(
                    url,
                    data=json_data,
                    method="POST",
                    headers={'Content-Type': 'application/json'}
                )
            else:
                raise APIError(f"Unsupported HTTP method: {method}")
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_data = response.read().decode('utf-8')
                return json.loads(response_data)
                
        except urllib.error.URLError as e:
            if isinstance(e, urllib.error.HTTPError):
                error_msg = f"HTTP {e.code}: {e.reason}"
                try:
                    error_body = e.read().decode('utf-8')
                    error_data = json.loads(error_body)
                    if 'detail' in error_data:
                        error_msg = error_data['detail']
                except Exception:
                    pass
                raise APIError(error_msg) from e
            else:
                raise APIError(f"Network error: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise APIError(f"Invalid JSON response: {e}") from e
        except Exception as e:
            raise APIError(f"Request failed: {e}") from e
    
    def get_configs(self) -> List[Dict[str, Any]]:
        """
        Get all configs from API.
        
        Returns:
            List of config dictionaries from API
            
        Raises:
            APIError: If request fails
        """
        try:
            response = self._make_request("GET", "/api/configs")
            # Handle different response formats
            if isinstance(response, list):
                return response
            elif isinstance(response, dict) and 'configs' in response:
                return response['configs']
            elif isinstance(response, dict):
                # Single config wrapped in dict
                return [response]
            else:
                return []
        except APIError:
            raise
    
    def upload_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload a config to API.
        
        Args:
            config_data: Config data dictionary (should match ConversionConfig structure)
            
        Returns:
            Response from API (typically includes id, created_at, etc.)
            
        Raises:
            APIError: If upload fails
        """
        return self._make_request("POST", "/api/configs", data=config_data)
    
    def test_connection(self) -> bool:
        """
        Test if API server is reachable.
        
        Returns:
            True if server is reachable, False otherwise
        """
        try:
            # Try to get configs (or a health endpoint if available)
            self._make_request("GET", "/api/configs")
            return True
        except APIError:
            return False


class ConfigSync:
    """Handles syncing configs between local cache and API."""
    
    def __init__(self, config_manager, api_client: Optional[APIClient] = None):
        """
        Initialize config sync.
        
        Args:
            config_manager: ConfigManager instance
            api_client: Optional APIClient instance (None if offline)
        """
        from config_manager import ConfigManager
        self.config_manager: ConfigManager = config_manager
        self.api_client: Optional[APIClient] = api_client
    
    def download_all_configs(self) -> tuple[int, int]:
        """
        Download all configs from API and save to local cache.
        
        Returns:
            Tuple of (downloaded_count, error_count)
            
        Raises:
            APIError: If API request fails
        """
        if not self.api_client:
            raise APIError("No API client configured (offline mode)")
        
        configs = self.api_client.get_configs()
        downloaded = 0
        errors = 0
        
        for config_dict in configs:
            try:
                # Convert API response to ConversionConfig
                # API might return config_data nested, or flat
                if 'config_data' in config_dict:
                    config_data = config_dict['config_data']
                    # Merge metadata
                    config_data['name'] = config_dict.get('name', config_data.get('name', 'Unnamed'))
                    config_data['description'] = config_dict.get('description', config_data.get('description', ''))
                    config_data['author'] = config_dict.get('author', config_data.get('author', ''))
                    config_data['remote_id'] = config_dict.get('id', config_dict.get('remote_id'))
                    config_data['is_local'] = False
                else:
                    # Flat structure
                    config_dict['is_local'] = False
                    config_data = config_dict
                
                # Create ConversionConfig
                from config_manager import ConversionConfig
                config = ConversionConfig.from_dict(config_data)
                
                # Save to local cache (will overwrite if exists)
                if self.config_manager.save_config(config):
                    downloaded += 1
                else:
                    errors += 1
            except Exception as e:
                print(f"Error processing config: {e}")
                errors += 1
        
        return downloaded, errors
    
    def upload_config(self, config_name: str) -> Dict[str, Any]:
        """
        Upload a local config to API.
        
        Args:
            config_name: Name of local config to upload
            
        Returns:
            API response dictionary
            
        Raises:
            APIError: If upload fails or config not found
        """
        if not self.api_client:
            raise APIError("No API client configured (offline mode)")
        
        # Load config from local cache
        config = self.config_manager.load_config(config_name)
        if not config:
            raise APIError(f"Config '{config_name}' not found locally")
        
        # Convert to dict for API
        config_dict = config.to_dict()
        
        # Upload to API
        response = self.api_client.upload_config(config_dict)
        
        # Update local config with remote_id if provided
        if 'id' in response:
            config.remote_id = response['id']
            config.is_local = False
            self.config_manager.save_config(config)
        
        return response
