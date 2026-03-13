"""
management command: seed
─────────────────────────────────────────────────────────────────────────────
Seeds the database with realistic Findify test data for a Philippine university
campus lost-and-found system.

What gets created
─────────────────
  • 1 admin user          (admin / admin123)
  • 40 regular users
  • 200 reports           (mix of lost + found, all categories, all statuses)
  • ~80  match suggestions (AI-style scores, pending/confirmed/dismissed)
  • ~60  claim requests    (pending/approved/rejected with proof descriptions)
  • ~300 notifications     (realistic per-event)
  • ~150 audit log entries

Usage:
    python manage.py seed               # idempotent: skips if data already exists
    python manage.py seed --force       # wipes first, then seeds fresh
    python manage.py seed --users 50 --reports 300   # custom counts
"""

import random
from datetime import timedelta, date, time

from django.core.management.base import BaseCommand
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
#  FAKE DATA POOLS
# ─────────────────────────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Juan","Maria","Jose","Ana","Carlo","Liza","Miguel","Sofia","Ramon","Chloe",
    "Gabriel","Isabella","Luis","Patricia","Eduardo","Carmen","Antonio","Elena",
    "Fernando","Rosa","Ricardo","Luz","Manuel","Teresa","Roberto","Diana",
    "Andres","Melissa","Christian","Jasmine","Kevin","Angela","Mark","Nicole",
    "James","Kristine","Paul","Camille","John","Bianca","Dave","Trisha",
    "Alex","Rina","Eric","Sheila","Ryan","Jessa","Leo","Mia",
]

LAST_NAMES = [
    "Santos","Reyes","Cruz","Garcia","Ramos","Mendoza","Torres","Flores",
    "Dela Cruz","Lopez","Gonzales","Rodriguez","Martinez","Hernandez","Perez",
    "Aquino","Bautista","Villanueva","Castillo","Soriano","Navarro","Morales",
    "Pascual","Guevara","Aguilar","Lim","Tan","Uy","Chua","Sy",
    "Macaraeg","Padilla","Alcantara","Velasquez","Ramirez","Salazar","Fuentes",
    "Cabrera","Miranda","Ferrer","Magno","De Leon","Del Rosario","Ocampo",
]

CAMPUS_LOCATIONS = [
    "Main Library",
    "Engineering Building",
    "Science Complex",
    "Student Center",
    "Cafeteria",
    "Gymnasium",
    "Administration Building",
    "IT Building",
    "Arts & Sciences Hall",
    "Medicine Building",
    "Business School",
    "Covered Court",
    "Parking Lot A",
    "Parking Lot B",
    "Dormitory 1",
    "Dormitory 2",
    "Chapel",
    "Oval / Track",
    "Swimming Pool Area",
    "Research Center",
]

LOCATION_DETAILS = [
    "Near the entrance",
    "Second floor restroom",
    "Ground floor lobby",
    "Beside the vending machines",
    "Outside Room 201",
    "Rooftop garden",
    "Basement level",
    "Study room 3",
    "Computer lab 2",
    "Near the bulletin board",
    "Main hallway",
    "Emergency exit door",
    "Faculty lounge area",
    None, None, None,   # ~30% chance of no detail
]

REPORT_DATA = {
    "Electronics": {
        "items": [
            ("Black iPhone 14 Pro", "Apple", "Black"),
            ("Samsung Galaxy S23 Ultra", "Samsung", "Phantom Black"),
            ("Laptop bag with Lenovo ThinkPad", "Lenovo", "Silver"),
            ("Wireless earbuds case", "Apple", "White"),
            ("Portable charger 20000mAh", "Anker", "Black"),
            ("HP laptop", "HP", "Silver"),
            ("ASUS ROG gaming laptop", "ASUS", "Black"),
            ("iPad Air 5th gen", "Apple", "Blue"),
            ("Sony WH-1000XM5 headphones", "Sony", "Black"),
            ("USB-C hub adapter", "Baseus", "Gray"),
            ("Xiaomi smartwatch", "Xiaomi", "Black"),
            ("Digital camera Canon EOS", "Canon", "Black"),
            ("Nintendo Switch", "Nintendo", "Red & Blue"),
            ("Huawei Matebook", "Huawei", "Space Gray"),
            ("Google Pixel 7", "Google", "Obsidian"),
        ],
        "descriptions": [
            "Lost in the library while studying. Has a cracked screen protector.",
            "Left on a table during a group study session. Screen lock enabled.",
            "Misplaced after a laboratory class. Has college sticker on lid.",
            "Dropped somewhere near the cafeteria. Case has a scratch on left side.",
            "Forgot in a classroom after an exam. Blue phone case with lanyard attached.",
        ],
    },
    "Wallets & Bags": {
        "items": [
            ("Brown leather wallet", None, "Brown"),
            ("Black backpack with initials JR", None, "Black"),
            ("Red crossbody bag", None, "Red"),
            ("Blue sling bag", None, "Blue"),
            ("Beige tote bag", None, "Beige"),
            ("Black bifold wallet", None, "Black"),
            ("Green messenger bag", None, "Green"),
            ("Floral pouch bag", None, "Multicolor"),
            ("Navy leather briefcase", None, "Navy"),
            ("Pink mini backpack", None, "Pink"),
        ],
        "descriptions": [
            "Contains student ID, two ATM cards, and cash. Very important.",
            "Has laptop, notebooks, and charger inside. Name tag on zipper.",
            "Lost near the gym after PE class. Contains water bottle and towel.",
            "Forgotten in a lecture hall. Has keychain and personal items.",
            "Dropped while running to class. Contains important documents.",
        ],
    },
    "Keys": {
        "items": [
            ("Car key with Toyota fob", "Toyota", "Black"),
            ("House key bundle with blue tag", None, "Silver"),
            ("Dormitory key with yellow tag", None, "Gold"),
            ("Locker key set #247", None, "Silver"),
            ("Motorcycle key Honda", "Honda", "Black"),
            ("Key with anime charm", None, "Silver"),
            ("Apartment key ring with 3 keys", None, "Silver"),
        ],
        "descriptions": [
            "Key has a distinctive green rubber tag. Very urgently needed.",
            "Lost after a morning class. Has a basketball keychain attached.",
            "Misplaced in the restroom area. Has a small stuffed toy attached.",
            "Dropped near the vending machine. Has initials engraved.",
            "Fell from pocket while sitting in the cafeteria.",
        ],
    },
    "Clothing": {
        "items": [
            ("Gray hoodie with university logo", None, "Gray"),
            ("Black PE uniform shirt", None, "Black"),
            ("Blue denim jacket", None, "Blue"),
            ("White lab gown", None, "White"),
            ("Yellow varsity jacket", None, "Yellow"),
            ("Maroon sports jersey #10", None, "Maroon"),
            ("Beige cardigan", None, "Beige"),
            ("School uniform blazer", None, "Dark Blue"),
        ],
        "descriptions": [
            "Left in the gymnasium after practice. Has name stitched inside.",
            "Forgotten in a cubicle. Has ink stains on the front pocket.",
            "Lost during a field trip. Has a small tear on the left sleeve.",
            "Misplaced after changing for PE class. Has phone pocket inside.",
            "Left hanging in the locker area. Has university emblem patch.",
        ],
    },
    "Jewelry": {
        "items": [
            ("Gold necklace with cross pendant", None, "Gold"),
            ("Silver bracelet with name engraving", None, "Silver"),
            ("Pearl earrings pair", None, "White"),
            ("Rosegold ring with gemstone", None, "Rose Gold"),
            ("Analog watch Seiko 5", "Seiko", "Silver"),
            ("Black rubber bracelet", None, "Black"),
            ("Diamond stud earrings", None, "Silver"),
        ],
        "descriptions": [
            "Very sentimental item given by grandmother. Please return.",
            "Fell off while doing lab work. Has engraving of a date inside.",
            "Lost near the restroom area. Has unique clasp mechanism.",
            "Misplaced after sports activity. Has distinct pattern.",
            "Lost during a school event. Extremely important to owner.",
        ],
    },
    "Documents": {
        "items": [
            ("Student ID card", None, None),
            ("Passport and immigration papers", None, None),
            ("Academic transcript folder", None, "Beige"),
            ("Driver's license", None, None),
            ("Medical certificate envelope", None, "White"),
            ("Scholarship documents folder", None, "Yellow"),
            ("Birth certificate copy", None, "White"),
        ],
        "descriptions": [
            "Very important document. Please return to admin office immediately.",
            "Contains identification that is urgently needed for enrollment.",
            "Lost during registration week. Has stapled forms inside.",
            "Dropped near the registrar's office. Needs to be returned ASAP.",
            "Important for graduation requirements. Please contact owner.",
        ],
    },
    "Other": {
        "items": [
            ("Prescription glasses", None, "Black"),
            ("Water bottle stainless steel", None, "Blue"),
            ("Umbrella with floral print", None, "Multicolor"),
            ("Lunch box with blue lid", None, "Blue"),
            ("Stethoscope", None, "Silver"),
            ("Scientific calculator Casio FX-991", "Casio", "Black"),
            ("Art supply kit", None, "Multicolor"),
            ("Badminton racket pair", "Yonex", "Black"),
            ("Book: Fundamentals of Nursing 9th ed.", None, "Blue"),
            ("Planner / agenda 2025", None, "Brown"),
        ],
        "descriptions": [
            "Urgently needed for classes. Has sticker of favorite band on it.",
            "Has owner's name written inside. Medication inside — please return.",
            "Lost during break time. Has distinctive scratches on one side.",
            "Misplaced after a study session. Has sticky note with phone number.",
            "Dropped while rushing to class. Has sentimental value.",
        ],
    },
}

FOUND_STORED_AT_OPTIONS = [
    "Turned in to the Security Office",
    "Left at the Information Desk",
    "With me, available for pickup",
    "Submitted to the Dean's Office",
    "At the Guard House (Main Gate)",
    "Library Lost & Found box",
    "Student Affairs Office",
    "Kept safe, please message me",
]

PROOF_DESCRIPTIONS = [
    "I can describe the exact contents of the wallet including the amount of cash inside.",
    "I have the original purchase receipt for this item dated {date}.",
    "This has my name engraved/written on the inside. I can also show photos.",
    "I can provide the serial number: {serial}. Also have purchase box at home.",
    "The password/PIN for this device is known to me. Can unlock it in person.",
    "I have the IMEI number registered in my name. Can show proof from settings.",
    "I recognize this by the specific scratch on the bottom-left corner.",
    "The keychain attached was a gift — I have photos of me holding it.",
    "My student ID number is written inside: {id_num}.",
    "I have matching item at home (bought as a pair). Can bring for comparison.",
    "I know the exact content of the bag including the specific notebooks.",
    "I have photos taken the same day showing me wearing/using this item.",
    "I can describe the unique distinguishing mark on the inside that only the owner would know.",
    "The item has a security mark/UV stamp I applied myself when I bought it.",
]

ADMIN_RESPONSES = {
    "approved": [
        "Ownership verified. The claimant provided sufficient proof.",
        "Confirmed match — claimant knew details only the owner would know.",
        "Approved. Purchase receipt and item description match.",
        "Claimant unlocked device on-site. Item returned.",
        "ID number and item description verified. Claim granted.",
    ],
    "rejected": [
        "Unable to verify ownership. Description did not match item.",
        "Insufficient proof provided. Please resubmit with purchase receipt or serial number.",
        "Claim rejected — another claimant provided stronger documentation.",
        "The details you provided do not match our records of this item.",
        "Please visit the admin office in person with a valid ID to process this claim.",
    ],
}

NOTIFICATION_TEMPLATES = {
    "report_received": {
        "title": "Report Received",
        "messages": [
            "Your {type} report for '{item}' has been received and is now open.",
            "We've received your report about '{item}'. Our team will review it shortly.",
            "Your {type} item report for '{item}' is now live on Findify.",
        ],
    },
    "under_review": {
        "title": "Report Under Review",
        "messages": [
            "Your report for '{item}' is now being reviewed by our team.",
            "An admin is currently reviewing your '{item}' report.",
            "Status update: '{item}' report has moved to Under Review.",
        ],
    },
    "matched": {
        "title": "Potential Match Found!",
        "messages": [
            "Great news! A potential match was found for your '{item}' report.",
            "We found a possible match for '{item}'. Please check your report for details.",
            "Your '{item}' may have been found! A match has been confirmed.",
        ],
    },
    "claim_received": {
        "title": "New Claim Submitted",
        "messages": [
            "A claim has been submitted for your found item '{item}'.",
            "Someone has claimed ownership of '{item}'. Under admin review.",
            "New claim request received for '{item}'.",
        ],
    },
    "claim_approved": {
        "title": "Claim Approved",
        "messages": [
            "Your claim for '{item}' has been approved. Please coordinate pickup.",
            "Great news! Your ownership claim for '{item}' was verified and approved.",
            "Claim approved — '{item}' is ready for pickup. Contact admin for schedule.",
        ],
    },
    "claim_rejected": {
        "title": "Claim Not Approved",
        "messages": [
            "Your claim for '{item}' was not approved this time. Check admin notes.",
            "We could not verify your claim for '{item}'. Please resubmit with more proof.",
            "Claim for '{item}' rejected. Visit the admin office for more information.",
        ],
    },
    "new_report": {
        "title": "New Report Submitted",
        "messages": [
            "A new {type} report was submitted: '{item}'.",
            "New {type}: '{item}' reported by a user. Please review.",
            "New submission: {type} report for '{item}' awaiting review.",
        ],
    },
    "new_claim": {
        "title": "New Claim Awaiting Review",
        "messages": [
            "A new claim was filed for '{item}'. Please review.",
            "New ownership claim submitted for '{item}'. Action needed.",
            "Claim request for '{item}' needs admin review.",
        ],
    },
}

AUDIT_DETAILS = {
    "login":             "Login: @{user}",
    "logout":            "Logout: @{user}",
    "register":          "New registration: @{user}",
    "report_created":    "Created {type} report #{id}: '{item}'",
    "report_updated":    "Updated report #{id}: '{item}'",
    "report_deleted":    "Deleted report #{id}: '{item}'",
    "claim_submitted":   "Claim #{id} submitted by @{user} on report #{rid}",
    "claim_approved":    "Claim #{id} approved by admin. Report #{rid} → claimed",
    "claim_rejected":    "Claim #{id} rejected by admin. Reason provided.",
    "match_confirmed":   "Match confirmed: Lost#{lid} ↔ Found#{fid} (score: {score:.2f})",
    "match_dismissed":   "Match #{id} dismissed by admin",
    "user_banned":       "Admin banned @{user}",
    "user_unbanned":     "Admin unbanned @{user}",
    "password_change":   "@{user} changed their password",
}


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def rdate(days_back_min=1, days_back_max=180):
    """Return a random date within the past N days."""
    delta = random.randint(days_back_min, days_back_max)
    return timezone.now().date() - timedelta(days=delta)

def rdatetime(days_back_min=1, days_back_max=180):
    delta = random.randint(days_back_min * 24 * 60, days_back_max * 24 * 60)
    return timezone.now() - timedelta(minutes=delta)

def rtime():
    """Random plausible campus hour (7am–10pm)."""
    h = random.randint(7, 22)
    m = random.choice([0, 15, 30, 45])
    return time(h, m)

def pick(lst):
    return random.choice(lst)

def maybe(val, prob=0.5):
    """Return val with given probability, else None."""
    return val if random.random() < prob else None


# ─────────────────────────────────────────────────────────────────────────────
#  COMMAND
# ─────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Seed the database with realistic test data."

    def add_arguments(self, parser):
        parser.add_argument("--force",   action="store_true", help="Wipe existing data first")
        parser.add_argument("--users",   type=int, default=40,  help="Number of regular users (default 40)")
        parser.add_argument("--reports", type=int, default=200, help="Number of reports (default 200)")

    def handle(self, *args, **options):
        from api.models import (
            User, UserProfile, LostReport, ReportImage,
            MatchSuggestion, ClaimRequest, Notification, AuditLog,
        )

        if options["force"]:
            self.stdout.write("  Wiping existing data…")
            AuditLog.objects.all().delete()
            Notification.objects.all().delete()
            ClaimRequest.objects.all().delete()
            MatchSuggestion.objects.all().delete()
            ReportImage.objects.all().delete()
            LostReport.objects.all().delete()
            UserProfile.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write(self.style.SUCCESS("  ✓ Cleared\n"))

        # ── check if data already exists ──────────────────────────────────────
        if not options["force"] and User.objects.filter(is_superuser=False).exists():
            self.stdout.write(self.style.WARNING(
                "Data already exists. Use --force to wipe and re-seed.\n"
            ))
            return

        n_users   = options["users"]
        n_reports = options["reports"]

        # ─────────────────────────────────────────────────────────────────────
        # 1. ADMIN USER
        # ─────────────────────────────────────────────────────────────────────
        self.stdout.write("Creating admin user…")
        admin, _ = User.objects.get_or_create(username="admin")
        # Always force-update — fixes stale role if user existed before seeding
        admin.email      = "admin@findify.edu"
        admin.first_name = "Admin"
        admin.last_name  = "User"
        admin.role       = "ADMIN"
        admin.status     = "active"
        admin.is_staff   = True
        admin.set_password("admin123")
        admin.save()
        UserProfile.objects.get_or_create(user=admin)
        self.stdout.write(self.style.SUCCESS(f"  ✓ admin / admin123"))

        # ─────────────────────────────────────────────────────────────────────
        # 2. REGULAR USERS
        # ─────────────────────────────────────────────────────────────────────
        self.stdout.write(f"Creating {n_users} regular users…")
        users = []
        used_usernames = set()
        statuses = ["active"] * 85 + ["inactive"] * 10 + ["banned"] * 5   # weighted

        for i in range(n_users):
            fn = pick(FIRST_NAMES)
            ln = pick(LAST_NAMES)
            base = f"{fn.lower()}.{ln.lower().replace(' ', '')}"
            uname = base
            suffix = 1
            while uname in used_usernames:
                uname = f"{base}{suffix}"
                suffix += 1
            used_usernames.add(uname)

            u = User.objects.create_user(
                username   = uname,
                email      = f"{uname}@student.findify.edu",
                password   = "password123",
                first_name = fn,
                last_name  = ln,
                role       = "USER",
                status     = pick(statuses),
            )
            # Random created date
            u.date_joined = rdatetime(days_back_max=365)
            u.save(update_fields=["date_joined"])

            UserProfile.objects.get_or_create(
                user = u,
                defaults = dict(
                    phone_number = maybe(f"+639{random.randint(100000000,999999999)}", 0.6),
                    bio          = maybe(pick([
                        "Engineering student. Lost and found enthusiast.",
                        "Nursing student. Please help me find my stuff!",
                        "CS major. I report things I find.",
                        "Architecture student. Always losing my rulers.",
                        "Medical student. Very forgetful.",
                    ]), 0.4),
                ),
            )
            users.append(u)

        self.stdout.write(self.style.SUCCESS(f"  ✓ {n_users} users created"))

        # ─────────────────────────────────────────────────────────────────────
        # 3. REPORTS
        # ─────────────────────────────────────────────────────────────────────
        self.stdout.write(f"Creating {n_reports} reports…")

        # Status distribution (realistic: most are open/under_review)
        status_pool = (
            ["open"]         * 35 +
            ["under_review"] * 20 +
            ["matched"]      * 15 +
            ["claimed"]      * 15 +
            ["closed"]       * 10 +
            ["rejected"]     *  5
        )
        type_pool = ["lost"] * 60 + ["found"] * 40

        reports = []
        categories = list(REPORT_DATA.keys())
        # Make sure all categories are represented roughly equally
        cat_pool = categories * (n_reports // len(categories) + 1)
        random.shuffle(cat_pool)

        for i in range(n_reports):
            user   = pick(users)
            rtype  = pick(type_pool)
            cat    = cat_pool[i % len(cat_pool)]
            status = pick(status_pool)

            cat_data = REPORT_DATA[cat]
            item_tpl  = pick(cat_data["items"])
            item_name, brand, color = item_tpl
            desc      = pick(cat_data["descriptions"])

            report_dt = rdatetime(days_back_max=120)
            event_date = rdate(days_back_max=120)

            r = LostReport(
                user          = user,
                report_type   = rtype,
                item_name     = item_name,
                category      = cat,
                location      = pick(CAMPUS_LOCATIONS),
                location_detail = maybe(pick(LOCATION_DETAILS), 0.5),
                date_event    = event_date,
                time_event    = maybe(rtime(), 0.6),
                brand         = maybe(brand, 0.8) if brand else None,
                color         = maybe(color, 0.8) if color else None,
                description   = desc,
                distinguishing_features = maybe(pick([
                    "Has a sticker of a cat on the back.",
                    "Initials engraved: M.R.S.",
                    "Small crack on the bottom-left corner.",
                    "Blue nail polish mark on the back.",
                    "Serial number written in marker: SN-{:06d}".format(random.randint(100000, 999999)),
                    "Name tag inside: {}".format(user.get_full_name()),
                    "Distinctive scratch pattern on the surface.",
                    "Custom engraving done at the mall.",
                ]), 0.45),
                reward        = maybe("₱{:,}".format(random.choice([200, 300, 500, 1000, 1500, 2000])), 0.25)
                                if rtype == "lost" else None,
                contact_phone = maybe(f"+639{random.randint(100000000,999999999)}", 0.5)
                                if rtype == "lost" else None,
                is_urgent     = random.random() < 0.15,
                found_stored_at = pick(FOUND_STORED_AT_OPTIONS) if rtype == "found" else None,
                status        = status,
                admin_notes   = maybe(pick([
                    "Item is being held at the Admin Office. Please claim within 7 days.",
                    "Please bring your school ID when claiming this item.",
                    "Report verified. Awaiting claimant.",
                    "Duplicate report — consolidated with existing entry.",
                    "Item turned over to Security Office on {}".format(event_date.strftime("%B %d")),
                ]), 0.3) if status not in ("open",) else None,
                views         = random.randint(0, 250),
                date_reported = report_dt,
            )
            r.save()
            # Override auto_now fields via queryset update
            LostReport.objects.filter(pk=r.pk).update(date_reported=report_dt)
            reports.append(r)

        self.stdout.write(self.style.SUCCESS(f"  ✓ {n_reports} reports created"))

        # ─────────────────────────────────────────────────────────────────────
        # 4. MATCH SUGGESTIONS
        # ─────────────────────────────────────────────────────────────────────
        self.stdout.write("Creating match suggestions…")
        lost_reports  = [r for r in reports if r.report_type == "lost"]
        found_reports = [r for r in reports if r.report_type == "found"]

        suggestions = []
        used_pairs  = set()
        n_suggestions = min(80, len(lost_reports) * len(found_reports))

        attempts = 0
        while len(suggestions) < n_suggestions and attempts < n_suggestions * 5:
            attempts += 1
            lr = pick(lost_reports)
            fr = pick(found_reports)
            pair = (lr.pk, fr.pk)
            if pair in used_pairs:
                continue
            # Only match same category ~70% of time (rest are wrong guesses)
            if lr.category != fr.category and random.random() < 0.7:
                continue
            used_pairs.add(pair)

            score = round(random.uniform(0.20, 0.97), 2)
            confidence = "high" if score >= 0.75 else ("medium" if score >= 0.50 else "low")
            ms_status  = pick(["pending"] * 50 + ["confirmed"] * 30 + ["dismissed"] * 20)

            ms = MatchSuggestion(
                lost_report  = lr,
                found_report = fr,
                score        = score,
                confidence   = confidence,
                score_breakdown = {
                    "category": round(random.uniform(0.0, 0.35), 3),
                    "name":     round(random.uniform(0.0, 0.30), 3),
                    "location": round(random.uniform(0.0, 0.20), 3),
                    "date":     round(random.uniform(0.0, 0.15), 3),
                },
                status = ms_status,
            )
            ms.save()
            suggestions.append(ms)

            # If confirmed → update both reports to matched
            if ms_status == "confirmed":
                LostReport.objects.filter(pk=lr.pk).update(
                    status=LostReport.STATUS_MATCHED, matched_report=fr
                )
                LostReport.objects.filter(pk=fr.pk).update(
                    status=LostReport.STATUS_MATCHED, matched_report=lr
                )

        self.stdout.write(self.style.SUCCESS(f"  ✓ {len(suggestions)} match suggestions created"))

        # ─────────────────────────────────────────────────────────────────────
        # 5. CLAIM REQUESTS
        # ─────────────────────────────────────────────────────────────────────
        self.stdout.write("Creating claim requests…")
        claimable = [r for r in reports if r.status in ("matched", "claimed", "closed", "under_review")]
        random.shuffle(claimable)
        claimable = claimable[:60]

        claims = []
        for r in claimable:
            # Pick a claimant who isn't the report owner
            possible_claimants = [u for u in users if u.pk != r.user_id]
            if not possible_claimants:
                continue
            claimant = pick(possible_claimants)

            cl_status = pick(["pending"] * 45 + ["approved"] * 35 + ["rejected"] * 20)

            proof = pick(PROOF_DESCRIPTIONS).format(
                date   = rdate().strftime("%B %d, %Y"),
                serial = "SN-{:08d}".format(random.randint(10000000, 99999999)),
                id_num = "{}-{:05d}".format(random.randint(2019, 2024), random.randint(10000, 99999)),
            )

            cl = ClaimRequest(
                report            = r,
                claimant          = claimant,
                proof_description = proof,
                status            = cl_status,
                admin_response    = pick(ADMIN_RESPONSES[cl_status])
                                    if cl_status != "pending" else None,
            )
            cl.save()
            claims.append(cl)

            # Update report status to match claim
            if cl_status == "approved":
                LostReport.objects.filter(pk=r.pk).update(status="claimed")
            elif cl_status == "pending" and r.status not in ("claimed",):
                LostReport.objects.filter(pk=r.pk).update(status="under_review")

        self.stdout.write(self.style.SUCCESS(f"  ✓ {len(claims)} claim requests created"))

        # ─────────────────────────────────────────────────────────────────────
        # 6. NOTIFICATIONS
        # ─────────────────────────────────────────────────────────────────────
        self.stdout.write("Creating notifications…")
        notifs = []

        # user-facing: report_received for every report
        for r in random.sample(reports, min(150, len(reports))):
            tpl = pick(NOTIFICATION_TEMPLATES["report_received"]["messages"])
            Notification.objects.create(
                user       = r.user,
                notif_type = "report_received",
                report     = r,
                title      = NOTIFICATION_TEMPLATES["report_received"]["title"],
                message    = tpl.format(type=r.report_type, item=r.item_name),
                is_read    = random.random() < 0.6,
            )
            notifs.append(1)

        # status-change notifications for non-open reports
        for r in reports:
            if r.status == "under_review":
                tpl = pick(NOTIFICATION_TEMPLATES["under_review"]["messages"])
                Notification.objects.create(
                    user=r.user, notif_type="under_review", report=r,
                    title=NOTIFICATION_TEMPLATES["under_review"]["title"],
                    message=tpl.format(item=r.item_name),
                    is_read=random.random() < 0.5,
                )
            elif r.status in ("matched", "claimed"):
                tpl = pick(NOTIFICATION_TEMPLATES["matched"]["messages"])
                Notification.objects.create(
                    user=r.user, notif_type="matched", report=r,
                    title=NOTIFICATION_TEMPLATES["matched"]["title"],
                    message=tpl.format(item=r.item_name),
                    is_read=random.random() < 0.7,
                )

        # admin notifications for new reports
        for r in random.sample(reports, min(80, len(reports))):
            tpl = pick(NOTIFICATION_TEMPLATES["new_report"]["messages"])
            Notification.objects.create(
                user=admin, notif_type="new_report", report=r,
                title=NOTIFICATION_TEMPLATES["new_report"]["title"],
                message=tpl.format(type=r.report_type, item=r.item_name),
                is_read=random.random() < 0.75,
            )

        # claim-related notifications
        for cl in claims:
            # notify report owner of new claim
            tpl = pick(NOTIFICATION_TEMPLATES["claim_received"]["messages"])
            Notification.objects.create(
                user=cl.report.user, notif_type="claim_received",
                report=cl.report, claim=cl,
                title=NOTIFICATION_TEMPLATES["claim_received"]["title"],
                message=tpl.format(item=cl.report.item_name),
                is_read=random.random() < 0.6,
            )
            # notify claimant of result
            if cl.status == "approved":
                tpl = pick(NOTIFICATION_TEMPLATES["claim_approved"]["messages"])
                Notification.objects.create(
                    user=cl.claimant, notif_type="claim_approved",
                    report=cl.report, claim=cl,
                    title=NOTIFICATION_TEMPLATES["claim_approved"]["title"],
                    message=tpl.format(item=cl.report.item_name),
                    is_read=random.random() < 0.8,
                )
            elif cl.status == "rejected":
                tpl = pick(NOTIFICATION_TEMPLATES["claim_rejected"]["messages"])
                Notification.objects.create(
                    user=cl.claimant, notif_type="claim_rejected",
                    report=cl.report, claim=cl,
                    title=NOTIFICATION_TEMPLATES["claim_rejected"]["title"],
                    message=tpl.format(item=cl.report.item_name),
                    is_read=random.random() < 0.5,
                )
            # admin: new claim
            tpl = pick(NOTIFICATION_TEMPLATES["new_claim"]["messages"])
            Notification.objects.create(
                user=admin, notif_type="new_claim",
                report=cl.report, claim=cl,
                title=NOTIFICATION_TEMPLATES["new_claim"]["title"],
                message=tpl.format(item=cl.report.item_name),
                is_read=random.random() < 0.8,
            )

        n_notifs = Notification.objects.count()
        self.stdout.write(self.style.SUCCESS(f"  ✓ {n_notifs} notifications created"))

        # ─────────────────────────────────────────────────────────────────────
        # 7. AUDIT LOGS
        # ─────────────────────────────────────────────────────────────────────
        self.stdout.write("Creating audit log entries…")

        # login / logout / register events for users
        for u in random.sample(users, min(30, len(users))):
            for action in random.sample(["login", "logout", "register"], random.randint(1, 3)):
                actor_type = "admin" if u.role == "ADMIN" else "user"
                AuditLog.objects.create(
                    action     = action,
                    actor_type = actor_type,
                    actor      = u,
                    detail     = AUDIT_DETAILS[action].format(user=u.username),
                    ip         = f"192.168.{random.randint(0,255)}.{random.randint(1,254)}",
                )

        # report_created events
        for r in random.sample(reports, min(80, len(reports))):
            AuditLog.objects.create(
                action     = "report_created",
                actor_type = "user",
                actor      = r.user,
                report     = r,
                detail     = AUDIT_DETAILS["report_created"].format(
                    type=r.report_type, id=r.pk, item=r.item_name),
                ip=f"192.168.{random.randint(0,255)}.{random.randint(1,254)}",
            )

        # claim events
        for cl in random.sample(claims, min(40, len(claims))):
            AuditLog.objects.create(
                action     = "claim_submitted",
                actor_type = "user",
                actor      = cl.claimant,
                claim      = cl,
                report     = cl.report,
                detail     = AUDIT_DETAILS["claim_submitted"].format(
                    id=cl.pk, user=cl.claimant.username, rid=cl.report_id),
                ip=f"192.168.{random.randint(0,255)}.{random.randint(1,254)}",
            )
            if cl.status == "approved":
                AuditLog.objects.create(
                    action="claim_approved", actor_type="admin", actor=admin,
                    claim=cl, report=cl.report,
                    detail=AUDIT_DETAILS["claim_approved"].format(id=cl.pk, rid=cl.report_id),
                    ip=f"192.168.{random.randint(0,255)}.{random.randint(1,254)}",
                )
            elif cl.status == "rejected":
                AuditLog.objects.create(
                    action="claim_rejected", actor_type="admin", actor=admin,
                    claim=cl, report=cl.report,
                    detail=AUDIT_DETAILS["claim_rejected"].format(id=cl.pk, rid=cl.report_id),
                    ip=f"192.168.{random.randint(0,255)}.{random.randint(1,254)}",
                )

        # match events
        for ms in random.sample(suggestions, min(20, len(suggestions))):
            if ms.status == "confirmed":
                AuditLog.objects.create(
                    action="match_confirmed", actor_type="admin", actor=admin,
                    report=ms.lost_report,
                    detail=AUDIT_DETAILS["match_confirmed"].format(
                        lid=ms.lost_report_id, fid=ms.found_report_id, score=ms.score),
                    ip=f"192.168.{random.randint(0,255)}.{random.randint(1,254)}",
                )
            elif ms.status == "dismissed":
                AuditLog.objects.create(
                    action="match_dismissed", actor_type="admin", actor=admin,
                    report=ms.lost_report,
                    detail=AUDIT_DETAILS["match_dismissed"].format(id=ms.pk),
                    ip=f"192.168.{random.randint(0,255)}.{random.randint(1,254)}",
                )

        # ban/unban a few users
        banned_users = random.sample(users, min(5, len(users)))
        for u in banned_users:
            AuditLog.objects.create(
                action="user_banned", actor_type="admin", actor=admin,
                target_user=u,
                detail=AUDIT_DETAILS["user_banned"].format(user=u.username),
                ip=f"192.168.{random.randint(0,255)}.{random.randint(1,254)}",
            )

        n_logs = AuditLog.objects.count()
        self.stdout.write(self.style.SUCCESS(f"  ✓ {n_logs} audit log entries created"))

        # ─────────────────────────────────────────────────────────────────────
        # SUMMARY
        # ─────────────────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("═" * 48))
        self.stdout.write(self.style.SUCCESS("  ✅  Seed complete!"))
        self.stdout.write(self.style.SUCCESS("═" * 48))
        self.stdout.write(f"  Users         : {User.objects.filter(is_superuser=False).count()}")
        self.stdout.write(f"  Reports       : {LostReport.objects.count()} "
                          f"({LostReport.objects.filter(report_type='lost').count()} lost / "
                          f"{LostReport.objects.filter(report_type='found').count()} found)")
        self.stdout.write(f"  Match Sugg.   : {MatchSuggestion.objects.count()}")
        self.stdout.write(f"  Claims        : {ClaimRequest.objects.count()}")
        self.stdout.write(f"  Notifications : {Notification.objects.count()}")
        self.stdout.write(f"  Audit Logs    : {AuditLog.objects.count()}")
        self.stdout.write("")
        self.stdout.write("  Admin login:  admin  /  admin123")
        self.stdout.write("  User login:   any username  /  password123")
        self.stdout.write("")