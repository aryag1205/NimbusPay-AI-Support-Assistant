# Account Status Definitions (Internal Terminology Guide)

NimbusPay's risk systems may place a wallet under an **administrative escrow lock**. This is a protective status applied automatically when unusual activity is detected on an account.

While under an administrative escrow lock, outgoing transfers and withdrawals are suspended; incoming funds are still accepted and held in escrow. The status is typically reviewed by the risk team within 48-72 hours.

A wallet can be released from an administrative escrow lock once the account holder completes additional identity verification or the flagged activity is confirmed as legitimate.

Common triggers for an administrative escrow lock include: a sudden spike in outgoing transfers, a login from an unrecognized device combined with a large withdrawal attempt, or a report filed by another user.
