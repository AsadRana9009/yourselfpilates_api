import mimetypes
import os
import re

from django.http import FileResponse, Http404, HttpResponse

RANGE_RE = re.compile(r'bytes=(\d*)-(\d*)', re.IGNORECASE)
CHUNK_SIZE = 8192


def _guess_content_type(path, fallback='application/octet-stream'):
    return mimetypes.guess_type(path)[0] or fallback


def _file_chunks(path, start, length):
    """Yield the requested slice without loading it all into memory."""
    with open(path, 'rb') as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def parse_range(range_header, file_size):
    """
    Return (start, end) for a single-range request, or None to serve the whole
    file. Raises ValueError when the range cannot be satisfied.
    """
    if not range_header:
        return None

    match = RANGE_RE.match(range_header.strip())
    if not match:
        return None

    raw_start, raw_end = match.group(1), match.group(2)

    if not raw_start and not raw_end:
        return None

    if not raw_start:
        # Suffix form: "bytes=-500" means the last 500 bytes.
        length = int(raw_end)
        if length <= 0:
            raise ValueError('Unsatisfiable range')
        start = max(0, file_size - length)
        end = file_size - 1
    else:
        start = int(raw_start)
        end = int(raw_end) if raw_end else file_size - 1
        end = min(end, file_size - 1)

    if start >= file_size or start > end:
        raise ValueError('Unsatisfiable range')

    return start, end


def range_file_response(request, file_field, fallback_content_type='application/octet-stream'):
    """
    Serve a FileField honouring HTTP Range.

    Media players need `206 Partial Content` to jump to a position that has not
    been downloaded yet; without it, seeking only works inside the part of the
    file the browser happens to have buffered.
    """
    if not file_field:
        raise Http404('File not found')

    try:
        path = file_field.path
    except (NotImplementedError, ValueError):
        raise Http404('File not found')

    if not os.path.exists(path):
        raise Http404('File not found')

    file_size = os.path.getsize(path)
    content_type = _guess_content_type(path, fallback_content_type)

    try:
        byte_range = parse_range(request.META.get('HTTP_RANGE'), file_size)
    except ValueError:
        response = HttpResponse(status=416)
        response['Content-Range'] = f'bytes */{file_size}'
        response['Accept-Ranges'] = 'bytes'
        return response

    if byte_range is None:
        response = FileResponse(open(path, 'rb'), content_type=content_type)
        response['Content-Length'] = str(file_size)
        response['Accept-Ranges'] = 'bytes'
        return response

    start, end = byte_range
    length = end - start + 1
    response = FileResponse(
        _file_chunks(path, start, length),
        content_type=content_type,
        status=206,
    )
    response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
    response['Content-Length'] = str(length)
    response['Accept-Ranges'] = 'bytes'
    return response
