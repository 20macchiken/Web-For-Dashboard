In the backends scenario we use flask for communication between the frontend and database and some package use for adjusting the http requests like `request`, `CORS`, and more.


`python -m venv .venv` To create virutal environemnt (In the root folder or Backend folder is ok but must cd to correct path.)
`venv\Scripts\activate` This cmd for windows to enter virtual environment
`pip install requirements.txt` Once enter install the dependencies or package by this cmd to install package in this program use.

`py server.py` or `python server.py` to run the backend server 


**Note that we use supabase in this project some of the things that need to be setup or configure are 

`Proxmox`, `InfluxDB`, `Supabase` These three essential for the project right now to configure in the backends. 

Create .env file in the Backend Folder. These are the variables that we use (Only the name is provided in this READme.)

# This use to create Proxmox related system like Creating, Starting, Stoping, and Delete VMS.

PROXMOX_HOST={Your_url}
PROXMOX_USER={your_name}@{your_authrealm_inProxmox}
PROXMOX_TOKEN_NAME={your_token_name}
PROXMOX_TOKEN_VALUE={your_token_value}

SUPABASE_URL={Your_url}
SUPABASE_SERVICE_ROLE_KEY={your_service_role_key}

# InfluxDB Configuration for Alert System
# TODO: Replace these placeholder values with your actual InfluxDB credentials

INFLUXDB_URL={Your_url}
INFLUXDB_TOKEN={Your_token}
INFLUXDB_ORG={your_org}
INFLUXDB_BUCKET={your_bucket}

