# Environment Setup and Installation

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [requirements.txt](file://requirements.txt)
- [pyproject.toml](file://pyproject.toml)
- [Dockerfile](file://Dockerfile)
- [docker-compose.yml](file://docker-compose.yml)
- [trading_bot/config/settings.py](file://trading_bot/config/settings.py)
- [trading_bot/config/logging_config.py](file://trading_bot/config/logging_config.py)
- [trading_bot/main.py](file://trading_bot/main.py)
- [trading_bot/data/fetcher.py](file://trading_bot/data/fetcher.py)
- [train.py](file://train.py)
- [backtest.py](file://backtest.py)
- [test_minimal.py](file://test_minimal.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Step-by-Step Installation](#step-by-step-installation)
4. [Virtual Environment Setup](#virtual-environment-setup)
5. [Dependency Installation](#dependency-installation)
6. [Environment Variable Configuration](#environment-variable-configuration)
7. [Docker Containerization](#docker-containerization)
8. [Verification Steps](#verification-steps)
9. [Platform-Specific Considerations](#platform-specific-considerations)
10. [Optional Components](#optional-components)
11. [Troubleshooting Guide](#troubleshooting-guide)
12. [Conclusion](#conclusion)

## Introduction
This document provides comprehensive environment setup and installation guidance for the AI Trading Bot. It covers Python version requirements, dependency management via requirements.txt and pyproject.toml, Docker containerization, environment variable configuration, virtual environment setup, verification procedures, and troubleshooting for common installation issues.

## Prerequisites
- Python 3.11+ is required for the project.
- Git is recommended for cloning the repository.
- Optional: Docker and Docker Compose for containerized deployment.

**Section sources**
- [README.md:56-59](file://README.md#L56-L59)
- [pyproject.toml:10](file://pyproject.toml#L10)

## Step-by-Step Installation
Follow these steps to set up the AI Trading Bot environment:

1. Clone the repository and navigate to the project directory.
2. Create and activate a Python virtual environment.
3. Install dependencies using either requirements.txt or pyproject.toml.
4. Configure environment variables using the .env.example template.
5. Verify the installation by running the CLI help command.

**Section sources**
- [README.md:63-85](file://README.md#L63-L85)

## Virtual Environment Setup
Create a dedicated virtual environment to isolate dependencies:

- Create the virtual environment using your system's Python 3.11 interpreter.
- Activate the environment before installing dependencies.
- Keep the environment activated during development and execution.

**Section sources**
- [README.md:69-73](file://README.md#L69-L73)

## Dependency Installation
The project supports two primary dependency management approaches:

### Using requirements.txt
- Install all dependencies with pip using the provided requirements.txt.
- This method installs all packages listed under core, data/exchange, technical analysis, ML/RL, backtesting, logging/monitoring, and utilities categories.

**Section sources**
- [requirements.txt:1-46](file://requirements.txt#L1-L46)

### Using pyproject.toml (Editable Install)
- Install the project in editable mode using pip with the project root.
- This approach leverages the project metadata and dependencies defined in pyproject.toml.
- The pyproject.toml file specifies Python 3.11+ as the minimum requirement and lists all core dependencies.

**Section sources**
- [pyproject.toml:1-117](file://pyproject.toml#L1-L117)

## Environment Variable Configuration
Configure the application using environment variables loaded from a .env file:

- Copy the .env.example template to .env and edit it with your settings.
- Essential variables include exchange API credentials, trading mode, symbols, timeframe, initial capital, risk parameters, Redis connection settings, and notification tokens/webhooks.
- The settings module loads variables from .env and validates them, including symbol parsing, timeframe validation, and path normalization.

Key configuration areas:
- Exchange configuration: API keys and testnet flag
- Trading configuration: mode, symbols, timeframe, capital, leverage, and position limits
- Risk management: daily drawdown limits, position sizing, exposure, and volatility targets
- Data storage: directories for data, SQLite database, and Parquet storage
- Redis configuration: host, port, database number, and optional password
- Model configuration: type, path, training timesteps, learning rate, and batch size
- Notifications: Telegram and Discord credentials
- Logging and monitoring: log level, file path, dashboard port, and metrics port

**Section sources**
- [README.md:81-85](file://README.md#L81-L85)
- [trading_bot/config/settings.py:23-176](file://trading_bot/config/settings.py#L23-L176)

## Docker Containerization
The project includes Docker and Docker Compose configurations for containerized deployment:

### Dockerfile Highlights
- Uses the official Python 3.11 slim base image.
- Sets environment variables to optimize Python behavior in containers.
- Installs system-level build dependencies required for certain Python packages.
- Copies and installs Python dependencies from requirements.txt.
- Installs the project in editable mode.
- Creates persistent directories for data, models, and logs.
- Exposes the Streamlit dashboard port (8501).
- Includes a health check that verifies the application imports successfully.
- Defines a default command to display CLI help.

**Section sources**
- [Dockerfile:1-44](file://Dockerfile#L1-L44)

### Docker Compose Services
The docker-compose.yml defines the following services:

- trading-bot: Main trading bot service with volume mounts for data, models, and logs; configured to run in paper mode by default; depends on Redis; includes health checks.
- dashboard: Streamlit dashboard service exposing port 8501; shares data and logs volumes; runs the dashboard application.
- redis: Redis service using the redis:7-alpine image; persists data in a named volume; exposes port 6379.
- jupyter (optional): Research notebook service available when the "research" profile is enabled; mounts notebooks directory.

Volumes and networks:
- Named volume for Redis data persistence.
- Bridge network for inter-service communication.

**Section sources**
- [docker-compose.yml:1-79](file://docker-compose.yml#L1-L79)

## Verification Steps
After installation, verify your setup using these steps:

- Confirm Python version meets the 3.11+ requirement.
- Verify that all core modules and files exist as expected.
- Run the CLI help command to ensure the application imports and displays available commands.
- Check that the environment variables are correctly loaded by running the configuration command.
- For Docker setups, confirm that services start successfully and pass their health checks.

**Section sources**
- [test_minimal.py:116-135](file://test_minimal.py#L116-L135)
- [trading_bot/main.py:24-66](file://trading_bot/main.py#L24-L66)
- [Dockerfile:38-43](file://Dockerfile#L38-L43)

## Platform-Specific Considerations
- TA-Lib dependency: The requirements specify ta-lib>=0.4.28 with a platform_system condition excluding Windows. On Windows, this dependency will be skipped. Alternative technical analysis libraries or platform-specific installation methods may be required for Windows environments.
- Redis client compatibility: The project uses redis>=5.0.0 and hiredis>=2.2.0. Ensure compatibility with your platform's Redis server.
- ML framework dependencies: PyTorch and related ML libraries may have platform-specific wheels; ensure appropriate versions are available for your operating system.

**Section sources**
- [requirements.txt:19](file://requirements.txt#L19)
- [requirements.txt:14-15](file://requirements.txt#L14-L15)

## Optional Components
The project supports optional components that enhance functionality:

- Redis: Used for caching market data and intermediate computations; included in the Docker Compose stack.
- PostgreSQL: While not explicitly listed in the provided configuration files, PostgreSQL can be integrated as an alternative data store. If you choose to use PostgreSQL, configure the database connection settings in your .env file and adjust data storage components accordingly.
- Jupyter Notebook: An optional research service is available in the Docker Compose configuration under the "research" profile, enabling interactive model development and experimentation.

**Section sources**
- [docker-compose.yml:54-71](file://docker-compose.yml#L54-L71)

## Troubleshooting Guide
Common installation issues and resolutions:

- Import errors: Ensure all dependencies are installed using the requirements.txt or pyproject.toml approach.
- API connection errors: Verify that exchange API keys and testnet settings are correctly configured in the .env file.
- Out of memory: Reduce batch sizes or observation windows in configuration settings.
- Model not loading: Confirm the model file path is correct and accessible.
- Platform-specific dependency failures: On Windows, the absence of TA-Lib is expected; use alternative technical analysis implementations or adjust indicator sets.

**Section sources**
- [README.md:311-323](file://README.md#L311-L323)

## Conclusion
You now have the essential steps to set up the AI Trading Bot environment using either a local Python installation or Docker. Ensure your Python version meets the 3.11+ requirement, configure environment variables appropriately, and verify the installation using the provided verification steps. For Docker users, the compose file provides a ready-to-run setup with Redis and optional Jupyter support. Address platform-specific considerations, particularly around TA-Lib on Windows, and consult the troubleshooting guide for common issues.