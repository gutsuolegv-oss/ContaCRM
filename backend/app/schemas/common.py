from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

# Cod tehnic (ex. TVA12, declaratii_fiscale): litere latine, cifre, underscore.
Code = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50, pattern=r"^\w+$")
]

# Text obligatoriu, fără spații la capete, cu lungimea maximă a coloanei.
Name100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Name200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Name255 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InputModel(BaseModel):
    """Câmpurile necunoscute sunt refuzate (o greșeală de tipar nu trece neobservată)."""

    model_config = ConfigDict(extra="forbid")
