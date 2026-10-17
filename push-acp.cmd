@echo off
REM push-acp.cmd -- crash-free, unattended "git push" for this repo.
REM
REM Why this exists:
REM   Git for Windows defaults to http.sslBackend=schannel. In a non-interactive
REM   account (e.g. a sandbox account) schannel fails with
REM     schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)
REM   and, when a credential helper is in the chain, git-remote-https.exe dies with
REM   an "application error" dialog that needs a human click -- which breaks
REM   unattended runs.
REM
REM What this does instead:
REM   force the openssl TLS backend, clear credential.helper, and pass the token
REM   in the URL, so neither schannel nor a credential helper is ever used.
REM
REM Usage:
REM   push-acp.cmd                 (push current branch to main)
REM   push-acp.cmd main            (explicit refspec)
REM   set ACP_PUSH_PROXY=          (override/clear the proxy; default 127.0.0.1:7897)
REM   set ACP_PUSH_URL=<url>       (override the remote URL, e.g. a different repo)

setlocal enabledelayedexpansion

set "PROXY=%ACP_PUSH_PROXY%"
if "%PROXY%"=="" set "PROXY=http://127.0.0.1:7897"

set "URL=%ACP_PUSH_URL%"
if "%URL%"=="" (
  for /f "usebackq delims=" %%t in (`gh auth token`) do set "TOKEN=%%t"
  if "!TOKEN!"=="" (
    echo [push-acp] no token: run "gh auth login" first 1>&2
    exit /b 1
  )
  set "URL=https://x-access-token:!TOKEN!@github.com/furoute/acp-lite.git"
)

set "REFSPEC=%*"
if "%REFSPEC%"=="" set "REFSPEC=main"

git -C "%~dp0." ^
  -c http.sslBackend=openssl ^
  -c http.proxy=%PROXY% ^
  -c credential.helper= ^
  push "%URL%" %REFSPEC%
exit /b %ERRORLEVEL%
