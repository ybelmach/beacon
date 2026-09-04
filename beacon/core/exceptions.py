from http import HTTPStatus


class AppError(Exception):
    """Base domain error."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    slug: str = "internal-server-error"
    default_detail: str = "An error occurred"

    def __init__(self, detail: str | None = None) -> None:
        self.detail: str = detail or self.default_detail
        super().__init__(self.detail)


class BadRequestError(AppError):
    status_code = HTTPStatus.BAD_REQUEST
    slug = "bad-request"
    default_detail = "Bad request"


class UnauthorizedError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    slug = "unauthorized"
    default_detail = "Unauthorized"


class ForbiddenError(AppError):
    status_code = HTTPStatus.FORBIDDEN
    slug = "forbidden"
    default_detail = "Forbidden"


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    slug = "not-found"
    default_detail = "Resource not found"


class ConflictError(AppError):
    status_code = HTTPStatus.CONFLICT
    slug = "conflict"
    default_detail = "Conflict"


class GoneError(AppError):
    status_code = HTTPStatus.GONE
    slug = "gone"
    default_detail = "Gone"


class UnprocessableEntityError(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_CONTENT
    slug = "unprocessable-entity"
    default_detail = "Unprocessable entity"


class TooManyRequestsError(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    slug = "too-many-requests"
    default_detail = "Too many requests"
