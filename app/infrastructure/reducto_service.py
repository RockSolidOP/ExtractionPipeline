from __future__ import annotations

import copy
from pathlib import Path
from typing import List, Dict, Any

from reducto import Reducto, ReductoError
import httpx

from app.core.settings import settings


def create_client(
    *,
    use_proxy: bool | None = None,
    proxy_url: str | None = None,
    connect_timeout: float | None = None,
    read_timeout: float | None = None,
    write_timeout: float | None = None,
    max_retries: int | None = None,
) -> Reducto:
    api_key = settings.reducto.api_key
    if not api_key:
        raise ReductoError(
            "REDUCTO_API_KEY is not set. Provide it via environment variable or .env file."
        )
    use_proxy = settings.reducto.use_proxy if use_proxy is None else use_proxy
    proxy_url = settings.reducto.proxy_url if proxy_url is None else proxy_url
    connect_timeout = settings.reducto.connect_timeout if connect_timeout is None else connect_timeout
    read_timeout = settings.reducto.read_timeout if read_timeout is None else read_timeout
    write_timeout = settings.reducto.write_timeout if write_timeout is None else write_timeout
    pool_timeout = settings.reducto.pool_timeout
    max_retries = settings.reducto.max_retries if max_retries is None else max_retries

    timeout = httpx.Timeout(
        connect=connect_timeout,
        read=read_timeout,
        write=write_timeout,
        pool=pool_timeout,
    )
    client_kwargs = {
        "follow_redirects": True,
        "timeout": timeout,
        "trust_env": False,
    }
    if use_proxy and proxy_url:
        client_kwargs["proxy"] = proxy_url
    http_client = httpx.Client(**client_kwargs)

    return Reducto(api_key=api_key, http_client=http_client, max_retries=max_retries, timeout=timeout)


def parse_document(client: Reducto, file_path: Path, page_number: int) -> dict:
    upload_url = client.upload(file=file_path)
    adv = copy.deepcopy(settings.reducto.advanced_options)
    adv["page_range"] = {"start": page_number, "end": page_number}
    result = client.parse.run(
        document_url=upload_url,
        options=settings.reducto.options,
        advanced_options=adv,
        experimental_options=settings.reducto.experimental_options,
    )
    return result.model_dump()


def parse_document_range(client: Reducto, file_path: Path, start_page: int, end_page: int) -> dict:
    upload_url = client.upload(file=file_path)
    adv = copy.deepcopy(settings.reducto.advanced_options)
    s = int(start_page)
    e = int(end_page)
    if e < s:
        s, e = e, s
    adv["page_range"] = {"start": s, "end": e}
    result = client.parse.run(
        document_url=upload_url,
        options=settings.reducto.options,
        advanced_options=adv,
        experimental_options=settings.reducto.experimental_options,
    )
    return result.model_dump()


def extract_with_schema(
    client: Reducto,
    file_path: Path,
    *,
    schema: dict,
    start_page: int,
    end_page: int,
    system_prompt: str,
) -> dict:
    upload_url = client.upload(file=file_path)
    adv = copy.deepcopy(settings.reducto.advanced_options)
    s = int(start_page)
    e = int(end_page)
    if e < s:
        s, e = e, s
    adv["page_range"] = {"start": s, "end": e}
    result = client.extract.run(
        document_url=upload_url,
        schema=schema,
        system_prompt=system_prompt,
        options=settings.reducto.options,
        advanced_options=adv,
        experimental_options=settings.reducto.experimental_options,
    )
    if hasattr(result, "model_dump") and callable(getattr(result, "model_dump")):
        return result.model_dump()
    if hasattr(result, "dict") and callable(getattr(result, "dict")):
        return result.dict()
    return result

