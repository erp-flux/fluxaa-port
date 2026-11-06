"""Tenancy and identity: ports, organisations, users, berths.

Multi-tenancy from day one (CDC orientation 1): every operational object belongs to exactly one
port. Freetown and Lomé are two tenants of the same platform; their templates, reference lists
and data are partitioned.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from .roles import ALL_ROLES, validate_roles


def pick(fr: str, en: str) -> str:
    """Return the label matching the active language, falling back to the other one."""
    lang = (translation.get_language() or "fr").lower()
    if lang.startswith("en"):
        return en or fr
    return fr or en


class Language(models.TextChoices):
    FR = "fr", "Français"
    EN = "en", "English"


class Port(models.Model):
    """A tenant: one port authority and its waters (quays, anchorage, offshore areas)."""

    code = models.CharField(_("UN/LOCODE"), max_length=10, unique=True, help_text=_("e.g. SLFNA, TGLFW"))
    name = models.CharField(_("name"), max_length=120)
    country = models.CharField(_("country (ISO 3166)"), max_length=2)
    timezone = models.CharField(_("time zone"), max_length=64, default="UTC")
    default_language = models.CharField(_("default language"), max_length=2, choices=Language.choices, default="fr")

    # Thresholds and delays — functional parameters (CDC EF-16), never code
    countersign_delay_minutes = models.PositiveIntegerField(
        _("countersignature delay (minutes)"), default=120,
        help_text=_("After this delay an unsigned milestone becomes a tacit countersignature (EF-3.4)."),
    )
    reminder_lead_hours = models.PositiveIntegerField(_("reminder lead time (hours)"), default=24)
    escalation_after_minutes = models.PositiveIntegerField(
        _("escalation after lateness (minutes)"), default=240,
        help_text=_("A normal task late beyond this threshold is escalated; a late blocking task is escalated at once."),
    )
    quantity_tolerance_pct = models.DecimalField(
        _("ship/shore tolerance (%)"), max_digits=5, decimal_places=3, default=Decimal("0.300")
    )
    ais_divergence_minutes = models.PositiveIntegerField(_("AIS divergence threshold (minutes)"), default=30)
    master_link_grace_hours = models.PositiveIntegerField(
        _("master link validity after departure (hours)"), default=24
    )
    master_link_max_days = models.PositiveIntegerField(_("master link maximum validity (days)"), default=30)
    party_link_max_days = models.PositiveIntegerField(
        _("party access link maximum validity (days)"), default=90,
        help_text=_("Account-less access of a terminal, surveyor, owner, provider or marine service: valid until the "
                    "closure of the call, at most this many days."),
    )
    retention_years = models.PositiveIntegerField(_("retention (years)"), default=10)
    digest_hour_local = models.PositiveSmallIntegerField(_("daily digest hour (local)"), default=7)
    security_authority_email = models.EmailField(
        _("security authority e-mail"), blank=True,
        help_text=_("Receives the nominative notifications of access to N4 records (EF-12.4)."),
    )
    ai_assistance_enabled = models.BooleanField(
        _("AI assistance enabled"), default=False,
        help_text=_("EF-17: extraction, draft remarks, consistency review and summaries — never a decision. "
                    "Requires the port's written agreement below and the platform's provider agreement."),
    )
    ai_agreement_reference = models.CharField(
        _("reference of the port's agreement for AI assistance"), max_length=200, blank=True,
        help_text=_("Contractual clause authorising the transfer of call data to the AI provider (EF-17)."),
    )
    # Map of the port waters (AIS board, EF-3.6 / ENF-8): the box drawn, and an optional chart excerpt behind it
    map_lat_min = models.DecimalField(_("map — southern latitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    map_lat_max = models.DecimalField(_("map — northern latitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    map_lon_min = models.DecimalField(_("map — western longitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    map_lon_max = models.DecimalField(_("map — eastern longitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    map_image = models.FileField(
        _("map background"), upload_to="maps/", blank=True,
        help_text=_("Optional chart or satellite excerpt covering exactly the box above (PNG or JPEG); "
                    "the port must hold the rights to publish it."),
    )
    ais_retention_days = models.PositiveIntegerField(
        _("AIS positions kept (days)"), default=30,
        help_text=_("Position reports older than this are purged; they are public broadcast data, not registry acts."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("port")
        verbose_name_plural = _("ports")

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    @property
    def has_map(self) -> bool:
        """The AIS board draws the port waters only once the box is configured (PARAMETRAGE.md §2)."""
        return all(v is not None for v in (self.map_lat_min, self.map_lat_max, self.map_lon_min, self.map_lon_max)) \
            and self.map_lat_min < self.map_lat_max and self.map_lon_min < self.map_lon_max


class Organization(models.Model):
    """An organisation active in a port. It may hold several roles (e.g. port authority: CAP, APO, DIR)."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="organizations", verbose_name=_("port"))
    name = models.CharField(_("name"), max_length=200)
    short_name = models.CharField(_("short name"), max_length=40, blank=True)
    kind = models.CharField(_("kind of party"), max_length=80, blank=True,
                            help_text=_("What the organisation is (pilotage, laboratory, bunker supplier…): a code of the "
                                        "suggested list or any other wording. The role, not the kind, carries the rights."))
    allowed_roles = models.JSONField(_("roles this organisation may hold"), default=list, blank=True)
    email = models.EmailField(_("e-mail"), blank=True)
    phone = models.CharField(_("phone (escalations)"), max_length=40, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["port", "name"], name="uniq_org_name_per_port")]
        verbose_name = _("organisation")
        verbose_name_plural = _("organisations")

    def __str__(self) -> str:
        return self.short_name or self.name

    @property
    def kind_label(self) -> str:
        from django.utils.translation import get_language

        from .parties import kind_label

        return kind_label(self.kind, (get_language() or "fr")[:2]) if self.kind else ""

    def clean(self):
        unknown = validate_roles(self.allowed_roles)
        if unknown:
            raise ValidationError({"allowed_roles": _("Unknown roles: %(r)s") % {"r": ", ".join(unknown)}})


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("An e-mail address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("full_name", "Platform operator")
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """A named person (or a technical integration account) belonging to one organisation."""

    username = None
    first_name = None
    last_name = None
    email = models.EmailField(_("e-mail"), unique=True)
    full_name = models.CharField(_("full name"), max_length=200)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="users",
        verbose_name=_("organisation"),
    )
    roles = models.JSONField(_("roles the user may exercise"), default=list, blank=True)
    language = models.CharField(_("language"), max_length=2, choices=Language.choices, blank=True)
    phone = models.CharField(_("mobile phone"), max_length=40, blank=True)
    is_port_admin = models.BooleanField(
        _("functional administrator of the port"), default=False,
        help_text=_("May edit templates, request types, reference lists and thresholds of their port (EF-16)."),
    )
    is_integration = models.BooleanField(_("technical integration account"), default=False)
    integration_scopes = models.JSONField(_("integration scopes"), default=list, blank=True)
    mfa_secret_encrypted = models.TextField(blank=True, editable=False)
    mfa_enabled = models.BooleanField(_("two-factor authentication enabled"), default=False)
    notify_digest_only = models.BooleanField(
        _("daily digest for normal tasks"), default=True,
        help_text=_("Blocking tasks and escalations are always notified in real time and cannot be muted (EF-6.3)."),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]
    objects = UserManager()

    class Meta:
        ordering = ["full_name"]
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self) -> str:
        return self.full_name or self.email

    @property
    def port(self) -> Port | None:
        return self.organization.port if self.organization_id else None

    @property
    def role_set(self) -> frozenset[str]:
        return frozenset(r for r in (self.roles or []) if r in ALL_ROLES)

    @property
    def requires_mfa_login(self) -> bool:
        """Deciding roles (ENF-3.1) — and anyone who administers accounts or settings: whoever can reset another
        person's second factor must hold one."""
        return bool(self.role_set & set(settings.FLUXAA_MFA_REQUIRED_ROLES)) or bool(
            self.is_port_admin or self.is_staff or self.is_superuser)

    def save(self, *args, **kwargs):
        if self.is_port_admin:
            self.is_staff = True  # functional administrators use the settings screens
        super().save(*args, **kwargs)

    def get_full_name(self) -> str:
        return self.full_name or self.email

    def get_short_name(self) -> str:
        return (self.full_name or self.email).split(" ")[0]

    def clean(self):
        super().clean()
        unknown = validate_roles(self.roles)
        if unknown:
            raise ValidationError({"roles": _("Unknown roles: %(r)s") % {"r": ", ".join(unknown)}})
        if self.organization_id:
            allowed = set(self.organization.allowed_roles or [])
            extra = set(self.roles or []) - allowed
            if extra:
                raise ValidationError(
                    {"roles": _("The organisation cannot hold these roles: %(r)s") % {"r": ", ".join(sorted(extra))}}
                )

    # --- two-factor secret, encrypted at rest with a key derived from FLUXAA_SIGNING_KEY ---
    def set_mfa_secret(self, secret: str) -> None:
        from .crypto import encrypt_main

        self.mfa_secret_encrypted = encrypt_main(secret)

    def get_mfa_secret(self) -> str:
        from .crypto import decrypt_main

        return decrypt_main(self.mfa_secret_encrypted) if self.mfa_secret_encrypted else ""


class Berth(models.Model):
    """A resource of the port where a tanker operates: quay/jetty, anchorage, offshore buoy, STS area."""

    class Kind(models.TextChoices):
        JETTY = "JETTY", _("Quay / jetty")
        ANCHORAGE = "ANCHORAGE", _("Anchorage (roads)")
        SPM = "SPM", _("Offshore buoy (SPM / CBM)")
        STS_AREA = "STS_AREA", _("Offshore STS area")

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="berths", verbose_name=_("port"))
    code = models.CharField(_("code"), max_length=30)
    name_fr = models.CharField(_("name (French)"), max_length=150)
    name_en = models.CharField(_("name (English)"), max_length=150)
    kind = models.CharField(_("type"), max_length=12, choices=Kind.choices)
    max_loa_m = models.DecimalField(_("max LOA (m)"), max_digits=6, decimal_places=1, null=True, blank=True)
    max_draft_m = models.DecimalField(_("max draft (m)"), max_digits=5, decimal_places=2, null=True, blank=True)
    max_dwt = models.PositiveIntegerField(_("max DWT"), null=True, blank=True)
    weather_limits = models.JSONField(
        _("weather limits"), default=dict, blank=True,
        help_text=_('e.g. {"wind_kn": 25, "swell_m": 2.0, "current_kn": 2.5, "visibility_nm": 1}'),
    )
    has_vapour_recovery = models.BooleanField(_("vapour recovery system"), default=False)
    latitude = models.DecimalField(_("latitude"), max_digits=9, decimal_places=6, null=True, blank=True,
                                   help_text=_("Centre of the berth or area, drawn on the AIS board."))
    longitude = models.DecimalField(_("longitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    radius_m = models.PositiveIntegerField(_("radius (m)"), null=True, blank=True,
                                           help_text=_("Extent of an anchorage or STS area around its centre."))
    notes = models.TextField(_("notes"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["port", "kind", "code"]
        constraints = [models.UniqueConstraint(fields=["port", "code"], name="uniq_berth_code_per_port")]
        verbose_name = _("berth / area")
        verbose_name_plural = _("berths / areas")

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    @property
    def name(self) -> str:
        return pick(self.name_fr, self.name_en)


class AttemptWindow(models.Model):
    """Failed attempts at a guessable secret (password, two-factor code, master access code) in the current
    window, per hashed key (apps.core.throttle). Technical table: no personal data is stored in clear."""

    key = models.CharField(max_length=64, unique=True)
    started_at = models.DateTimeField()
    failures = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("attempt window")
