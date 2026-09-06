# Archived PoC Scripts

These scripts document the first monolithic prototypes and are kept only for
historical comparison in the thesis:

- `poc_dp_ksa_legacy.py`: synthetic-data simulation with Laplace thresholding;
- `poc_real_dp_ksa_legacy.py`: first end-to-end local/cloud prototype;
- `download_model_legacy.py`: standalone Hugging Face downloader.

They are not part of the supported implementation and are excluded from the
lint target. Use `poc/run_pipeline.py` (or its compatibility wrapper
`poc/poc_real_dp_ksa.py`) for current experiments.
