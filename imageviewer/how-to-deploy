# Update & install Python
sudo apt update
sudo apt -y install python3-pip python3-venv

# App setup
mkdir -p ~/azure-image-viewer && cd ~/azure-image-viewer
# copy the three files above into this folder...

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Configure env
cp .env.example .env
nano .env   # fill values

# Run (port 8501 by default)
streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501
