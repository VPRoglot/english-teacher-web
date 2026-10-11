from app.core.errors import AppError


class UnsupportedImage(AppError):
    status_code = 415
    code = "unsupported_media_type"
    message = "Поддерживаются только изображения JPEG, PNG и WebP"


class FileTooLarge(AppError):
    status_code = 413
    code = "file_too_large"
    message = "Файл слишком большой: до 5 МБ и не больше 40 мегапикселей"


class StorageUnavailable(AppError):
    status_code = 503
    code = "storage_unavailable"
    message = "Хранилище файлов недоступно. Попробуйте позже"
