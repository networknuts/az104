import os
from typing import Optional, Tuple, List

import streamlit as st
from azure.storage.blob import ContainerClient
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Azure Blob Image Viewer", layout="wide")

# ---------- Auth helpers ----------
def get_container_client(
    container_name: str,
    connection_string: Optional[str],
    account_url: Optional[str],
    sas_token: Optional[str],
) -> ContainerClient:
    # 1) Connection string auth
    if connection_string:
        return ContainerClient.from_connection_string(
            conn_str=connection_string,
            container_name=container_name
        )
    # 2) Account URL + SAS token (read-only)
    if account_url and sas_token:
        # Ensure token doesn't start with '?'
        sas = sas_token[1:] if sas_token.startswith("?") else sas_token
        return ContainerClient(
            account_url=f"{account_url}?{sas}",
            container_name=container_name,
            credential=None
        )
    # 3) Public container (anonymous)
    if account_url and not sas_token:
        return ContainerClient(
            account_url=account_url,
            container_name=container_name,
            credential=None
        )
    raise ValueError("No valid authentication method provided.")


# ---------- Blob paging ----------
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff")

def list_image_blobs_page(
    container: ContainerClient,
    prefix: str,
    continuation_token: Optional[str],
    page_size: int
) -> Tuple[List[str], Optional[str]]:
    pager = container.list_blobs(
        name_starts_with=prefix or None,
        results_per_page=page_size
    ).by_page(continuation_token=continuation_token)

    # Get one page
    page = next(pager, [])
    names = [b.name for b in page if b.name.lower().endswith(IMAGE_EXTS)]
    next_token = pager.continuation_token  # type: ignore
    return names, next_token


@st.cache_data(show_spinner=False)
def fetch_image_bytes(container_url: str, container_name: str, blob_name: str,
                      connection_string: Optional[str], account_url: Optional[str], sas_token: Optional[str]) -> bytes:
    # Create a short-lived client inside the cache scope
    container = get_container_client(container_name, connection_string, account_url, sas_token)
    return container.get_blob_client(blob_name).download_blob().readall()


# ---------- UI ----------
with st.sidebar:
    st.header("Configuration")

    # Read possible env vars (choose one auth path)
    default_container = os.getenv("AZURE_CONTAINER", "")
    default_account_url = os.getenv("AZURE_ACCOUNT_URL", "")  # e.g. https://<account>.blob.core.windows.net
    default_sas = os.getenv("AZURE_SAS_TOKEN", "")            # starts with or without '?'
    default_conn = os.getenv("AZURE_CONNECTION_STRING", "")

    container_name = st.text_input("Container name", value=default_container, placeholder="my-container")
    account_url = st.text_input("Account URL (for SAS/public)", value=default_account_url, placeholder="https://<account>.blob.core.windows.net")
    sas_token = st.text_input("Container/Account SAS token (read-only)", value=default_sas, type="password", placeholder="sv=...&ss=bfqt&...")
    connection_string = st.text_input("Connection string (alternative to SAS)", value=default_conn, type="password")

    prefix = st.text_input("Prefix filter (optional)", value="")
    page_size = st.number_input("Images per page", min_value=3, max_value=60, value=12, step=3)

    if "continuation" not in st.session_state:
        st.session_state.continuation = None
    if "last_query_sig" not in st.session_state:
        st.session_state.last_query_sig = ""

    if st.button("Reset paging"):
        st.session_state.continuation = None

st.title("🖼️ Azure Blob Image Viewer")

# Build a signature of the query to reset continuation when inputs change
query_sig = f"{container_name}|{account_url}|{bool(sas_token)}|{bool(connection_string)}|{prefix}|{page_size}"
if st.session_state.last_query_sig != query_sig:
    st.session_state.continuation = None
    st.session_state.last_query_sig = query_sig

if not container_name:
    st.info("Enter at least a **container name** (and auth above).")
    st.stop()

try:
    container_client = get_container_client(container_name, connection_string or None, account_url or None, sas_token or None)
except Exception as e:
    st.error(f"Auth/connection error: {e}")
    st.stop()

# Page controls
col_a, col_b, col_c = st.columns([1, 1, 6])
with col_a:
    prev_click = st.button("⬅️ Prev", use_container_width=True)
with col_b:
    next_click = st.button("Next ➡️", use_container_width=True)

# We need to remember a stack of tokens to support "Prev"
if "token_stack" not in st.session_state:
    st.session_state.token_stack = []

# If moving next, push current token and advance
if next_click:
    st.session_state.token_stack.append(st.session_state.continuation)

# If moving prev, pop one and set as continuation
if prev_click and st.session_state.token_stack:
    # Going back means we need the token before the *previous* page
    _ = st.session_state.token_stack.pop()  # discard current
    st.session_state.continuation = st.session_state.token_stack.pop() if st.session_state.token_stack else None

# Get a page of blob names
try:
    names, next_token = list_image_blobs_page(container_client, prefix, st.session_state.continuation, page_size)
except Exception as e:
    st.error(f"Listing error: {e}")
    st.stop()

# Render grid
if not names:
    st.warning("No images found on this page. Adjust filters or paging.")
else:
    cols = st.columns(3)
    for i, blob_name in enumerate(names):
        with cols[i % 3]:
            try:
                img_bytes = fetch_image_bytes(
                    container_url=container_client.url,
                    container_name=container_name,
                    blob_name=blob_name,
                    connection_string=connection_string or None,
                    account_url=account_url or None,
                    sas_token=sas_token or None
                )
                st.image(img_bytes, caption=blob_name, use_container_width=True)
                with st.expander("Details"):
                    st.code(blob_name)
            except Exception as e:
                st.error(f"Failed to load {blob_name}: {e}")

# Update continuation only when moving forward
if next_click:
    st.session_state.continuation = next_token

# Footer
st.caption("Auth modes: public container • Container SAS (read-only) • connection string. This app downloads bytes via SDK, so images are not exposed as public URLs.")
