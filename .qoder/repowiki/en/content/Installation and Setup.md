# Installation and Setup

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [requirements.txt](file://requirements.txt)
- [pyproject.toml](file://pyproject.toml)
- [Dockerfile](file://Dockerfile)
- [docker-compose.yml](file://docker-compose.yml)
- [trading_bot/main.py](file://trading_bot/main.py)
- [trading_bot/config/settings.py](file://trading_bot/config/settings.py)
- [trading_bot/config/logging_config.py](file://trading_bot/config/logging_config.py)
- [train.py](file://train.py)
- [backtest.py](file://backtest.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Manual Installation](#manual-installation)
4. [Docker Installation](#docker-installation)
5. [Environment Setup](#environment-setup)
6. [Initial Configuration](#initial-configuration)
7. [Usage Examples](#usage-examples)
8. [Troubleshooting](#troubleshooting)
9. [Docker Compose Services](#docker-compose-services)
10. [Conclusion](#conclusion)

## Introduction
This guide provides comprehensive installation and setup instructions for the AI Trading Bot. It covers prerequisites, manual and Docker-based deployments, environment setup, dependency installation, initial configuration, and troubleshooting. The project supports both local development and containerized deployment using Docker Compose.

## Prerequisites
- Python 3.11 or higher
- Git
- Optional: Docker and Docker Compose for containerized deployment

These requirements are documented in the project’s README under the Installation section.

**Section sources**
- [README.md:56-59](file://README.md#L56-L59)

## Manual Installation
Follow these steps to set up the project locally:

1. Clone the repository
   - Use Git to clone the repository and navigate into the project directory.

2. Create a virtual environment
   - Create a virtual environment to isolate dependencies.
   - Activate the virtual environment before installing dependencies.

3. Install dependencies
   - Install the required Python packages using the provided requirements file.
   - Alternatively, install the project in editable mode.

4. Configure environment
   - Copy the example environment file to .env and edit it to include your API keys and settings.

Notes:
- The README outlines the manual setup steps, including cloning, virtual environment creation, dependency installation, and environment configuration.
- The project metadata and dependencies are defined in pyproject.toml, including the minimum Python version requirement.
- The requirements file lists the exact dependency versions used by the project.

**Section sources**
- [README.md:61-85](file://README.md#L61-L85)
- [pyproject.toml:10](file://pyproject.toml#L10)
- [requirements.txt:1-46](file://requirements.txt#L1-L46)

## Docker Installation
The project includes a Dockerfile and Docker Compose configuration for containerized deployment. Use the following commands to build and run the services:

- Build and run with Docker Compose
- View logs
- Stop services

The Docker Compose file defines three primary services: trading-bot, dashboard, and redis. An optional jupyter service is also available for research workflows.

Key points:
- The Dockerfile sets up a Python 3.11 slim base image, installs system dependencies, copies and installs Python dependencies, and exposes the Streamlit dashboard port.
- The Docker Compose file mounts persistent volumes for data, models, and logs, and passes environment variables via .env.

**Section sources**
- [README.md:87-98](file://README.md#L87-L98)
- [Dockerfile:1-44](file://Dockerfile#L1-L44)
- [docker-compose.yml:1-79](file://docker-compose.yml#L1-L79)

## Environment Setup
The project uses environment variables managed by pydantic-settings. The configuration is loaded from a .env file and validated at runtime.

Important configuration areas:
- Exchange credentials and testnet settings
- Trading mode, symbols, timeframe, and capital
- Risk management parameters
- Data storage locations (directories for SQLite, Parquet, and logs)
- Redis connection settings
- Model configuration (type, path, timesteps)
- Notification integrations (Telegram, Discord)
- Logging level and file location
- Monitoring ports

The configuration module validates inputs such as timeframe and parses comma-separated symbol lists. It also ensures required directories exist.

**Section sources**
- [trading_bot/config/settings.py:23-176](file://trading_bot/config/settings.py#L23-L176)

## Initial Configuration
To configure the environment for the first time:

1. Create the .env file
   - Copy the example environment file to .env in the project root.

2. Edit .env
   - Add your Binance API keys and set testnet usage.
   - Configure trading parameters such as symbols, timeframe, and initial capital.
   - Set risk management parameters (daily drawdown, position size, risk per trade).
   - Define model configuration (model type and timesteps).
   - Optionally enable notifications via Telegram or Discord.
   - Adjust logging level and file location.

3. Verify configuration
   - Use the CLI to display current configuration and confirm values are applied.

Notes:
- The README provides a template for editing .env with exchange API keys, trading configuration, risk parameters, model settings, and optional notification tokens.
- The CLI includes a config command to print the effective configuration at runtime.

**Section sources**
- [README.md:81-85](file://README.md#L81-L85)
- [README.md:100-128](file://README.md#L100-L128)
- [trading_bot/main.py:48-66](file://trading_bot/main.py#L48-L66)

## Usage Examples
Once installed, you can use the CLI to manage the bot. The README documents common commands for help, configuration inspection, data fetching, training, backtesting, running in paper or live modes, and launching the dashboard.

Examples include:
- Showing help and configuration
- Fetching historical data
- Training models with optional hyperparameter optimization
- Running backtests with walk-forward and Monte Carlo analysis
- Executing paper and live trading runs
- Launching the Streamlit dashboard

Training and backtesting scripts are also provided for convenience.

**Section sources**
- [README.md:130-196](file://README.md#L130-L196)
- [train.py:43-97](file://train.py#L43-L97)
- [backtest.py:16-106](file://backtest.py#L16-L106)

## Troubleshooting
Common installation and runtime issues, along with suggested resolutions:

- Import errors
  - Symptom: Missing modules during import.
  - Resolution: Reinstall dependencies using the requirements file or install the project in editable mode.

- API connection errors
  - Symptom: Failures connecting to the exchange.
  - Resolution: Verify API keys and testnet settings in .env.

- Out of memory
  - Symptom: Memory-related failures during training or data processing.
  - Resolution: Reduce batch size or observation window in configuration.

- Model not loading
  - Symptom: Errors when loading a trained model file.
  - Resolution: Confirm the model file path is correct and accessible.

Additional guidance:
- Use the CLI to inspect configuration and verify environment variables are loaded.
- Review logs written to the configured log file path.

**Section sources**
- [README.md:309-323](file://README.md#L309-L323)
- [trading_bot/main.py:48-66](file://trading_bot/main.py#L48-L66)
- [trading_bot/config/logging_config.py:13-79](file://trading_bot/config/logging_config.py#L13-L79)

## Docker Compose Services
The Docker Compose setup defines the following services:

- trading-bot
  - Purpose: Runs the trading bot in paper mode by default.
  - Behavior: Mounts data, models, and logs directories; loads environment from .env; depends on redis; health-checked.
  - Ports: Exposed via the Dockerfile default command.

- dashboard
  - Purpose: Hosts the Streamlit monitoring dashboard.
  - Behavior: Mounts data and logs; exposes port 8501; runs the dashboard script.

- redis
  - Purpose: Provides caching and session storage.
  - Behavior: Uses an Alpine Linux image; persists data in a named volume.

- jupyter (optional)
  - Purpose: Research and experimentation environment.
  - Behavior: Available when the research profile is enabled; mounts notebooks directory.

Volume and network definitions:
- Named volume for redis data persistence.
- Bridge network for inter-service communication.

Logs and lifecycle:
- Logs can be viewed using docker-compose logs -f trading-bot.
- Services restart automatically unless explicitly stopped.

**Section sources**
- [docker-compose.yml:3-79](file://docker-compose.yml#L3-L79)
- [Dockerfile:35-44](file://Dockerfile#L35-L44)

## Conclusion
You now have the information needed to install and run the AI Trading Bot either manually or via Docker. Ensure Python 3.11+ is installed, create a virtual environment, install dependencies, configure .env, and use the CLI or Docker Compose to operate the system. For containerized deployments, leverage the provided Dockerfile and docker-compose.yml to manage services, logs, and persistent storage.