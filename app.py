import json
import os

import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")

st.title("Resume Extractor")
files = st.file_uploader(
    "Choose one file, or select several for a batch",
    accept_multiple_files=True,
    type=["pdf", "docx", "png", "jpg", "jpeg"],
)

if files and st.button("Extract"):
    with st.spinner("Processing..."):
        try:
            if len(files) == 1:
                f = files[0]
                r = requests.post(f"{API}/extract", files={"file": (f.name, f.getvalue())}, timeout=300)
            else:
                r = requests.post(
                    f"{API}/extract/batch",
                    files=[("files", (f.name, f.getvalue())) for f in files],
                    timeout=900,
                )
        except requests.RequestException as e:
            st.error(f"Could not reach the API at {API}: {e}")
            st.stop()

    if not r.ok:
        st.error(r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text)
    elif len(files) == 1:
        result = r.json()
        st.caption(f"parsing: {result['parsing']} | tools: {', '.join(result['tools_used'])}")
        if result["missing_fields"]:
            st.warning("Missing: " + ", ".join(result["missing_fields"]))
        st.json(result["data"])
        st.download_button("Download JSON", json.dumps(result, indent=2), f"{files[0].name}.json")
    else:
        summary = r.json()
        a, b, c = st.columns(3)
        a.metric("Succeeded", summary["succeeded"])
        b.metric("Failed", summary["failed"])
        c.metric("Incomplete", summary["incomplete"])
        st.dataframe([
            {
                "file": e["file"],
                "status": e["status"],
                "parsing": e.get("parsing"),
                "missing": ", ".join(e.get("missing_fields", [])),
                "error": e.get("error"),
                "seconds": e["seconds"],
            }
            for e in summary["files"]
        ])
        for e in summary["files"]:
            if e["status"] == "success":
                with st.expander(e["file"]):
                    st.json(e["data"])