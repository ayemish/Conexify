"""
PDM Main Entry Point

Command-line interface and application bootstrapping.
"""

import argparse
import logging
import sys

def setup_environment():
    """Set up environment and logging"""
    from .observability.logging import setup_logging
    from .config import settings
    
    setup_logging(
        level=settings.logging.level,
        format=settings.logging.format,
        include_trace=settings.logging.include_trace_id,
    )
    
    return settings


def run_api_server():
    """Run the FastAPI server"""
    import uvicorn
    from .config import settings
    
    setup_environment()
    
    uvicorn.run(
        "predictive_maintenance.api.app:app",
        host=settings.api.host,
        port=settings.api.port,
        workers=settings.api.workers,
        reload=settings.api.reload,
        log_level=settings.logging.level.lower(),
    )


def run_init_db():
    """Initialize the database"""
    settings = setup_environment()
    logger = logging.getLogger(__name__)
    
    from .persistence.database import init_db
    
    logger.info("Initializing database...")
    init_db(drop_existing=False)
    logger.info("Database initialized successfully")


def run_tests():
    """Run the test suite"""
    import pytest
    sys.exit(pytest.main(["-v", "predictive_maintenance/tests/"]))


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="PDM - Predictive Maintenance System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pdm serve          Start the API server
  pdm init-db        Initialize the database
  pdm test           Run the test suite
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    serve_parser.add_argument("--workers", type=int, default=4, help="Number of workers")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    # init-db command
    subparsers.add_parser("init-db", help="Initialize the database")
    
    # test command
    subparsers.add_parser("test", help="Run the test suite")
    
    args = parser.parse_args()
    
    if args.command == "serve":
        run_api_server()
    elif args.command == "init-db":
        run_init_db()
    elif args.command == "test":
        run_tests()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
