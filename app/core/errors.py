from fastapi import HTTPException, status

class AppError(HTTPException):
    pass

def bad_request(code: str, message: str):
    raise AppError(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": code, "message": message})

def unauthorized(message: str = "Unauthorized"):
    raise AppError(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "UNAUTHORIZED", "message": message})

def conflict(code: str, message: str):
    raise AppError(status_code=status.HTTP_409_CONFLICT, detail={"code": code, "message": message})

def not_found(code: str, message: str):
    raise AppError(status_code=status.HTTP_404_NOT_FOUND, detail={"code": code, "message": message})
