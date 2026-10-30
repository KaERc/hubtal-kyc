from django.utils.cache import add_never_cache_headers


class NoStoreMiddleware:
    """Every page here shows personal data and changes after each action, so the browser must not keep a copy.
    Without this, Back shows a page as it was before an upload or a status change, or after signing out."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        add_never_cache_headers(response)
        return response
