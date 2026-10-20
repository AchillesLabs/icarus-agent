"""Authenticated Google REST API clients for Calendar, Gmail, and Google Drive."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

import httpx

CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3"
GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1"
DRIVE_BASE_URL = "https://www.googleapis.com/drive/v3"


class GoogleCalendarApiClient:
    """Authenticated client for Google Calendar REST API v3."""

    def __init__(self, access_token: str, http_client: httpx.Client | None = None) -> None:
        self.access_token = access_token
        self._http_client = http_client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def list_events(
        self,
        calendar_id: str = "primary",
        time_min: str | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Query calendar events starting from time_min."""
        params: dict[str, Any] = {
            "maxResults": min(max(max_results, 1), 50),
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        if time_min and time_min.lower() != "today":
            params["timeMin"] = time_min

        client = self._http_client or httpx.Client(timeout=15.0)
        should_close = self._http_client is None
        try:
            url = f"{CALENDAR_BASE_URL}/calendars/{calendar_id}/events"
            resp = client.get(url, headers=self._headers(), params=params)
            if resp.status_code == 401:
                raise PermissionError(
                    "Google Calendar token expired or unauthorized. Re-authentication required."
                )
            if resp.status_code != 200:
                raise RuntimeError(f"Google Calendar API error ({resp.status_code}): {resp.text}")
            data = resp.json()
            return data.get("items", [])
        finally:
            if should_close:
                client.close()

    def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        description: str = "",
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Schedule a new event in Google Calendar."""
        event_body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time} if "T" in start_time else {"date": start_time},
            "end": {"dateTime": end_time} if "T" in end_time else {"date": end_time},
        }

        client = self._http_client or httpx.Client(timeout=15.0)
        should_close = self._http_client is None
        try:
            url = f"{CALENDAR_BASE_URL}/calendars/{calendar_id}/events"
            resp = client.post(url, headers=self._headers(), json=event_body)
            if resp.status_code == 401:
                raise PermissionError("Google Calendar token expired or unauthorized.")
            if resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"Failed to create Google Calendar event ({resp.status_code}): {resp.text}"
                )
            return resp.json()
        finally:
            if should_close:
                client.close()


class GmailApiClient:
    """Authenticated client for Gmail REST API v1."""

    def __init__(self, access_token: str, http_client: httpx.Client | None = None) -> None:
        self.access_token = access_token
        self._http_client = http_client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def search_messages(
        self,
        query: str = "is:unread",
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Search Gmail inbox and return message summaries with snippet and headers."""
        params = {"q": query, "maxResults": min(max(max_results, 1), 20)}
        client = self._http_client or httpx.Client(timeout=15.0)
        should_close = self._http_client is None
        try:
            url = f"{GMAIL_BASE_URL}/users/me/messages"
            resp = client.get(url, headers=self._headers(), params=params)
            if resp.status_code == 401:
                raise PermissionError(
                    "Gmail token expired or unauthorized. Re-authentication required."
                )
            if resp.status_code != 200:
                raise RuntimeError(f"Gmail API search error ({resp.status_code}): {resp.text}")

            data = resp.json()
            message_stubs = data.get("messages", [])
            results: list[dict[str, Any]] = []

            for stub in message_stubs[:max_results]:
                msg_id = stub.get("id")
                if not msg_id:
                    continue
                detail_url = f"{GMAIL_BASE_URL}/users/me/messages/{msg_id}?format=metadata"
                detail_resp = client.get(detail_url, headers=self._headers())
                if detail_resp.status_code == 200:
                    detail = detail_resp.json()
                    headers = {
                        h.get("name", "").lower(): h.get("value", "")
                        for h in detail.get("payload", {}).get("headers", [])
                    }
                    results.append(
                        {
                            "id": msg_id,
                            "snippet": detail.get("snippet", ""),
                            "subject": headers.get("subject", "No Subject"),
                            "from": headers.get("from", "Unknown"),
                            "date": headers.get("date", ""),
                        }
                    )
            return results
        finally:
            if should_close:
                client.close()

    def send_message(self, to: str, subject: str, body: str) -> dict[str, Any]:
        """Send an RFC 2822 email via Gmail REST API."""
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        client = self._http_client or httpx.Client(timeout=15.0)
        should_close = self._http_client is None
        try:
            url = f"{GMAIL_BASE_URL}/users/me/messages/send"
            resp = client.post(url, headers=self._headers(), json={"raw": raw})
            if resp.status_code == 401:
                raise PermissionError("Gmail token expired or unauthorized.")
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Gmail API send error ({resp.status_code}): {resp.text}")
            return resp.json()
        finally:
            if should_close:
                client.close()


class GoogleDriveApiClient:
    """Authenticated client for Google Drive REST API v3."""

    def __init__(self, access_token: str, http_client: httpx.Client | None = None) -> None:
        self.access_token = access_token
        self._http_client = http_client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def search_files(
        self,
        query: str = "",
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Search Google Drive files matching query (e.g. name contains 'budget' or mimeType)."""
        params: dict[str, Any] = {
            "pageSize": min(max(max_results, 1), 50),
            "fields": "files(id, name, mimeType, modifiedTime, size)",
        }
        if query:
            clean_q = query.replace("'", "\\'")
            params["q"] = f"name contains '{clean_q}' and trashed = false"

        client = self._http_client or httpx.Client(timeout=15.0)
        should_close = self._http_client is None
        try:
            url = f"{DRIVE_BASE_URL}/files"
            resp = client.get(url, headers=self._headers(), params=params)
            if resp.status_code == 401:
                raise PermissionError("Google Drive token expired or unauthorized.")
            if resp.status_code != 200:
                raise RuntimeError(f"Google Drive search error ({resp.status_code}): {resp.text}")
            data = resp.json()
            return data.get("files", [])
        finally:
            if should_close:
                client.close()

    def read_file_content(self, file_id: str, max_bytes: int = 50_000) -> str:
        """Read and return content of a text or document file from Google Drive."""
        client = self._http_client or httpx.Client(timeout=15.0)
        should_close = self._http_client is None
        try:
            url = f"{DRIVE_BASE_URL}/files/{file_id}?alt=media"
            resp = client.get(url, headers=self._headers())
            if resp.status_code == 401:
                raise PermissionError("Google Drive token expired or unauthorized.")
            if resp.status_code != 200:
                # If it's a Google Doc, export as plain text
                export_url = f"{DRIVE_BASE_URL}/files/{file_id}/export?mimeType=text/plain"
                export_resp = client.get(export_url, headers=self._headers())
                if export_resp.status_code == 200:
                    text = export_resp.text
                    return text[:max_bytes]
                raise RuntimeError(
                    f"Failed to read file from Google Drive ({resp.status_code}): {resp.text}"
                )
            text = resp.text
            return text[:max_bytes]
        finally:
            if should_close:
                client.close()
