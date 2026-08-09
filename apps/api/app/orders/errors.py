class OrderError(Exception):
    code = "order_error"


class OrderValidationError(OrderError):
    code = "order_validation_error"


class OrderConflict(OrderError):
    code = "order_conflict"


class OrderNotFound(OrderError):
    code = "order_not_found"
