from dataclasses import dataclass

@dataclass
class Transaction:
    date: str
    outflow: str
    inflow: str
    category: str
    account: str
    memo: str
    status: str
