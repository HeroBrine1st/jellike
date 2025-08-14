import logging

class HeaderFormatter(logging.Formatter):
    def format(self, record):
        # to match uvicorn logger
        header = record.levelname
        if record.name != "Jellike":
            header = f"{header} ({record.name})"
        header += ":"
        record.header = header.ljust(9)
        return super().format(record)
