# Board setup

How the Dragonwing IQ-9075 was prepared on 2026-11-13. Run these on the board during online setup, never at app start.

1. NPU packages: `sudo apt-get install --no-install-recommends libatomic1 qcom-fastrpc1 libqnn1`, then
   `sudo usermod -aG fastrpc ubuntu` and log in again.
2. `stage_zetic.sh all` downloads the ZETIC Ixian Hexagon SDK 0.2.1 (checksum pinned) and the four LFM3 IQ9
   packages into `~/zetic-demo`, verifying each package against its `SHA256SUMS`.
3. Replace `~/zetic-demo/run.py` with `run.py` from this folder. It is the reference wrapper with one line
   changed so its NPU evidence check matches what SDK 0.2.1 prints.
4. `python3 test_models.py` (copied into `~/zetic-demo`) sends one capped request per input type to each
   staged model and appends full results to `zetic-results.jsonl`.
5. Copy `sister_cli.py`, `sister_voice_demo.py`, `backend/`, `samples/` and
   `docs/sister-questionnaire-v1/` to `~/sister` on the board.

Staged and smoke-tested on the board: LFM3-1.7B, LFM3-Omni-2B, LFM3-Audio-2B. LFM3-VL-2B did not finish
downloading and was not tested; Sister does not use it.
