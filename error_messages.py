"""User-facing protocol error messages shared by the CLI and GUI."""

ER_MSG = (
    "OK.",
    "Unknown or unexpected command.",
    "Unknown user.",
    "Wrong password.",
    "Error building the file list.",
    "File does not exist.",
    "Error downloading the file.",
    "Anonymous users have no permission for this operation.",
    "File is too large.",
    "Error preparing the file for upload.",
    "Error uploading the file.",
    "Error deleting the file.",
    "Not enough quorum to confirm the operation.",
    "This server is not the primary.",
    "Cannot share a file with yourself.",
    "Registration is disabled.",
    "Invalid registration data.",
    "User is disabled.",
    "User already exists.",
    "Protocol line is too long.",
    "Revision conflict.",
)


def message(code):
    try:
        return ER_MSG[int(code)]
    except (IndexError, TypeError, ValueError):
        return "Error {}.".format(code)