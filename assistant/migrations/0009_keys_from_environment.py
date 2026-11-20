"""A provider's key leaves the database: it is read from the environment only.

Each provider names the variable of its key, set from what it is: its API's own variable when it speaks to its API's
own company, Alibaba's for Alibaba Cloud Model Studio (Qwen), and none for any other address (a proxy, another
compatible provider), so no key travels where it was not meant to until the staff choose one. The table of the keys
goes with what it held. On the way back the table returns empty and the variable goes.
"""

from urllib.parse import urlsplit

from django.db import migrations, models

#: The company domain of each API's own address, and the variable of its key.
KIND_DOMAINS = {
    "openai": ("openai.com", "OPENAI_API_KEY"),
    "anthropic": ("anthropic.com", "ANTHROPIC_API_KEY"),
    "gemini": ("googleapis.com", "GEMINI_API_KEY"),
    "deepseek": ("deepseek.com", "DEEPSEEK_API_KEY"),
}
ALIBABA_DOMAIN = "aliyuncs.com"


def within(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def key_variable_of(kind: str, base_url: str) -> str:
    host = (urlsplit(base_url).hostname or "") if base_url else ""
    domain, variable = KIND_DOMAINS.get(kind, ("", ""))
    if not base_url or (domain and within(host, domain)):
        return variable
    if kind == "openai" and within(host, ALIBABA_DOMAIN):
        return "DASHSCOPE_API_KEY"
    return ""


def name_key_variables(apps, schema_editor):
    providers = apps.get_model("assistant", "AIProvider").objects.using(schema_editor.connection.alias)
    for provider in providers.all():
        provider.key_variable = key_variable_of(provider.kind, provider.base_url)
        provider.save(update_fields=["key_variable"])


class Migration(migrations.Migration):

    dependencies = [
        ('assistant', '0008_retire_azure_speech'),
    ]

    operations = [
        # First, before any row of a provider changes: a change to a provider would leave the table's checks pending.
        migrations.DeleteModel(
            name='AIProviderCredential',
        ),
        migrations.AddField(
            model_name='aiprovider',
            name='key_variable',
            field=models.CharField(choices=[('OPENAI_API_KEY', 'OPENAI_API_KEY'), ('ANTHROPIC_API_KEY', 'ANTHROPIC_API_KEY'), ('GEMINI_API_KEY', 'GEMINI_API_KEY'), ('DEEPSEEK_API_KEY', 'DEEPSEEK_API_KEY'), ('DASHSCOPE_API_KEY', 'DASHSCOPE_API_KEY')], default='', help_text="The variable of erplora.com's environment that holds its key. Each provider of OpenAI's API reads its own.", max_length=32, verbose_name='key variable'),
            preserve_default=False,
        ),
        migrations.RunPython(name_key_variables, migrations.RunPython.noop),
    ]
