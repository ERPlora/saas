"""The OSS figures that both the notices (``billing.services.oss_notices``) and their mail (``billing.emails``) read.
No imports: the mail must never import the writes that send it."""

#: The share of the threshold whose passing tells the team to register in the OSS (it takes days).
OSS_WARNING_PERCENT = 80
