def start_services(self, recreate: bool = False) -> bool:
    """Start Docker services with permanent port allocation."""
    # Force remove any problematic containers before starting
    if recreate:
        self._force_remove_problematic_containers()

    # Load project configuration using backtracking
    from ..config import ConfigManager
    config_manager = ConfigManager.create_with_backtrack()
    config = config_manager.load()
    
    # Convert config to dict for required services detection
    config_dict = {
        "embedding_provider": config.embedding_provider,
        "ollama": config.ollama.__dict__ if hasattr(config, "ollama") else {},
        "qdrant": config.qdrant.__dict__ if hasattr(config, "qdrant") else {},
    }
    
    # Determine required services based on configuration
    required_services = self.get_required_services(config_dict)
    self.console.print(f"🔍 Required services: {', '.join(required_services)}")

    # Get project root from config
    project_root = Path(config.codebase_dir)
    
    # Check if we have permanent ports assigned to this project
    # If ports are 0, this is the first time - need to allocate new ports
    # If ports are non-zero, we have permanent ports - use them
    has_permanent_ports = any([
        config.project_ports.qdrant_port != 0,
        config.project_ports.ollama_port != 0,
        config.project_ports.data_cleaner_port != 0
    ])
    
    if has_permanent_ports:
        # We have permanent ports - check if services are healthy
        self.console.print("🔍 Found permanent ports - checking service health...")
        
        # Check if all required services are healthy
        all_healthy = True
        for service in required_services:
            try:
                # Get service URL using the permanent ports from config
                service_url = self._get_service_url(service)
                is_healthy = self.health_checker.is_service_healthy(service_url)
                self.console.print(f"🔍 {service} health check: {is_healthy}")
                if not is_healthy:
                    all_healthy = False
                    break
            except Exception as e:
                self.console.print(f"🔍 {service} health check failed: {e}")
                all_healthy = False
                break
        
        if all_healthy:
            self.console.print("✅ All required services are healthy with permanent ports")
            return True
        else:
            self.console.print("⚠️  Some services not healthy - will restart with permanent ports")
            # Use the permanent ports from config
            permanent_ports = {
                "qdrant_port": config.project_ports.qdrant_port,
                "ollama_port": config.project_ports.ollama_port,
                "data_cleaner_port": config.project_ports.data_cleaner_port,
            }
            # Filter to only required services
            filtered_ports = {}
            for service in required_services:
                port_key = f"{service.replace('-', '_')}_port"
                if port_key in permanent_ports and permanent_ports[port_key] != 0:
                    filtered_ports[port_key] = permanent_ports[port_key]
            
            return self._attempt_start_with_ports(
                required_services,
                self._generate_container_names(project_root),
                project_root,
                recreate,
                filtered_ports,
            )
    
    # First time - ports are 0, need to allocate new permanent ports
    self.console.print("🆕 First time setup - allocating permanent ports...")
    
    # Generate container names for this project
    container_names = self._generate_container_names(project_root)
    
    # Allocate new permanent ports
    allocated_ports = self._allocate_free_ports(container_names["project_hash"])
    
    # Save ports to config RIGHT AWAY - these are now our permanent ports
    self._update_config_with_ports(project_root, allocated_ports)
    self.console.print(f"💾 Saved permanent ports to config: {allocated_ports}")
    
    # Now start containers with these permanent ports
    return self._attempt_start_with_ports(
        required_services,
        container_names,
        project_root,
        recreate,
        allocated_ports,
    )