# Résumé IQ — W1-W9 Verification Report

**Date**: 2026-10-06 12:21:21
**Overall Status**: SOME FAILED

| ID | Test Suite | Status | Duration | Evidence Path |
|---|---|---|---|---|
| **W1** | Render parity (1440x900 & mobile, computed styles, zero console errors) | **FAIL** | 10.40s | `Error: Brand title must include Résumé with correct accent` |
| **W2** | Upload -> index -> chat (chunk equality, no duplicates, sources chip N>=1) | **FAIL** | 2.36s | `Error: [WinError 10061] No connection could be made because the target machine actively refused it` |
| **W3** | Streaming protocol (tokens over time, in-place node replacement, single scroll) | **FAIL** | 2.29s | `Error: [WinError 10061] No connection could be made because the target machine actively refused it` |
| **W4** | Guards & fallbacks ('hi', irrelevant Q smart fallback, no-doc guard) | **FAIL** | 2.29s | `Error: [WinError 10061] No connection could be made because the target machine actively refused it` |
| **W5** | Multi-turn query rewrite (pronoun resolution, Q2 alone control) | **FAIL** | 2.32s | `Error: [WinError 10061] No connection could be made because the target machine actively refused it` |
| **W6** | Session isolation & state ops (canary token protection, cross-user privacy) | **FAIL** | 2.42s | `Error: [WinError 10061] No connection could be made because the target machine actively refused it` |
| **W7** | ATS Resume intelligence & Analyze tabs (caching, JD not indexed) | **FAIL** | 2.23s | `Error: [WinError 10061] No connection could be made because the target machine actively refused it` |
| **W8** | Streamlit regression & manifest integrity (zero tampering) | **FAIL** | 0.00s | `Error: Protected file app.py missing!` |
| **W9** | Zero logic duplication (AST literal checks, no streamlit in server) | **PASS** | 0.22s | `verification/w9_*.txt / .png` |