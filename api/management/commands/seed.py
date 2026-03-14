"""
management command: seed
─────────────────────────────────────────────────────────────────────────────
Findify — Philippine university campus lost-and-found seeder.

DESIGN GUARANTEE
────────────────
Every matched pair:
  • has the EXACT SAME item_name on both the lost and found report
  • has coherent descriptions (same item, same location context, same features)
  • has the same category and color
  • uses the actual assigned user's real name (resolved at runtime via fill())
  • has found_date >= lost_date (within 0-3 days)

Usage:
    python manage.py seed                 # skip if data exists
    python manage.py seed --force         # wipe + reseed
    python manage.py seed --force --users 60
"""

import random
from datetime import timedelta, time as dtime

from django.core.management.base import BaseCommand
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
#  NAME POOLS
# ─────────────────────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "Juan","Maria","Jose","Ana","Carlo","Liza","Miguel","Sofia","Ramon","Chloe",
    "Gabriel","Isabella","Luis","Patricia","Eduardo","Carmen","Antonio","Elena",
    "Fernando","Rosa","Ricardo","Luz","Manuel","Teresa","Roberto","Diana",
    "Andres","Melissa","Christian","Jasmine","Kevin","Angela","Mark","Nicole",
    "James","Kristine","Paul","Camille","John","Bianca","Dave","Trisha",
    "Alex","Rina","Eric","Sheila","Ryan","Jessa","Leo","Mia",
    "Ken","Hazel","Renz","Abby","Lance","Gwen","Tim","Faith",
]
LAST_NAMES = [
    "Santos","Reyes","Cruz","Garcia","Ramos","Mendoza","Torres","Flores",
    "Dela Cruz","Lopez","Gonzales","Rodriguez","Martinez","Hernandez","Perez",
    "Aquino","Bautista","Villanueva","Castillo","Soriano","Navarro","Morales",
    "Pascual","Guevara","Aguilar","Lim","Tan","Uy","Chua","Sy",
    "Macaraeg","Padilla","Alcantara","Velasquez","Ramirez","Salazar","Fuentes",
    "Cabrera","Miranda","Ferrer","Magno","De Leon","Del Rosario","Ocampo",
]
FOUND_STORED_AT = [
    "Turned in to the Security Office",
    "Left at the Information Desk",
    "With me — available for pickup, please message",
    "Submitted to the Dean's Office",
    "Guard House (Main Gate)",
    "Library Lost & Found box",
    "Student Affairs Office",
    "Kept safely, please contact me to claim",
]
COURSES = [
    "BS Computer Science","BS Civil Engineering","BS Nursing","BS Architecture",
    "BS Business Administration","BS Fine Arts","BS Medicine","BS Education",
    "BS Information Technology","BA Communication","BS Psychology","BS Biology",
]

# ─────────────────────────────────────────────────────────────────────────────
#  PAIR TEMPLATES
#
#  Each entry is a dict with keys:
#    category, item_name, brand, color, location (where both lost & found)
#    lost_desc   — template string, uses {owner}, {owner_fn}, {owner_initials}
#    found_desc  — template string, uses {finder_fn}, {owner}, {owner_initials}
#    proof_desc  — template string for claim proof
#    feature     — distinguishing_features template
#    reward      — string or None
#
#  RULE: item_name is IDENTICAL on both sides. Descriptions are the same item,
#        just written from the loser's POV vs. the finder's POV.
# ─────────────────────────────────────────────────────────────────────────────
PAIR_TEMPLATES = [

    # ── ELECTRONICS ──────────────────────────────────────────────────────────
    dict(
        category="Electronics", item_name="iPhone 14 Pro", brand="Apple", color="Space Black",
        location="Main Library",
        feature="cracked screen protector, UP Diliman sticker on back, dog photo as lock screen",
        lost_desc=(
            "Lost my black iPhone 14 Pro at the Main Library 2nd floor while studying. "
            "Has a cracked screen protector and a UP Diliman sticker on the back. "
            "Lock screen shows a photo of my dog. Owner: {owner}."
        ),
        found_desc=(
            "Found a black iPhone 14 Pro on the 2nd floor reading area of the Main Library. "
            "Has a cracked screen protector and a university sticker on the back. "
            "Lock screen shows a dog photo. Phone was off. Turned in to Information Desk by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner}. My lock screen wallpaper is a photo of my golden retriever. "
            "I can provide my Apple ID email registered to this device and remotely ping it via Find My iPhone."
        ),
        reward="₱500",
    ),
    dict(
        category="Electronics", item_name="Samsung Galaxy S23 Ultra", brand="Samsung", color="Phantom Black",
        location="Engineering Building",
        feature="S-Pen attached, crack on top-right screen corner, green cracked silicone case",
        lost_desc=(
            "Lost my Samsung Galaxy S23 Ultra at the Engineering Building after our lab session. "
            "Has the S-Pen in the slot at the bottom. Screen has a crack on the top-right corner. "
            "Wrapped in a green silicone case that also has a crack on the side. Owner: {owner}."
        ),
        found_desc=(
            "Found a Samsung Galaxy S23 Ultra with a green cracked silicone case near Engineering Building Room 304. "
            "S-Pen is attached. Visible crack on the top-right screen corner. Found by {finder_fn}, "
            "screen was locked."
        ),
        proof_desc=(
            "I am {owner}. My initials are scratched on the S-Pen tip. "
            "I can provide the IMEI number and unlock the device with my fingerprint in person."
        ),
        reward="₱300",
    ),
    dict(
        category="Electronics", item_name="Lenovo ThinkPad E14 Laptop", brand="Lenovo", color="Silver",
        location="Cafeteria",
        feature="red electrical tape on lower-left corner, 'PROPERTY OF {owner_initials}' sticker on lid",
        lost_desc=(
            "Left my silver Lenovo ThinkPad E14 at a cafeteria table during lunch. "
            "Has a red electrical tape mark on the lower-left corner of the base and a sticker on the lid "
            "that reads 'PROPERTY OF {owner_initials}'. Contains my thesis files — very urgent. Owner: {owner}."
        ),
        found_desc=(
            "Found a silver Lenovo ThinkPad E14 at a table near the cafeteria exit. "
            "Has red electrical tape on the lower-left corner and a 'PROPERTY OF {owner_initials}' sticker on the lid. "
            "Brought to the Information Desk by {finder_fn}."
        ),
        proof_desc=(
            "The sticker reads 'PROPERTY OF {owner_initials}' — my initials (full name: {owner}). "
            "My name is also written inside the battery compartment. "
            "I can state the desktop wallpaper and provide the serial number from my receipt at home."
        ),
        reward="₱1,000",
    ),
    dict(
        category="Electronics", item_name="Apple AirPods Pro 2nd Gen", brand="Apple", color="White",
        location="Gymnasium",
        feature="'{owner_initials}' engraved on charging case lid, black marker dot on left earbud",
        lost_desc=(
            "Lost my white AirPods Pro 2nd gen charging case near the gymnasium after my morning jog. "
            "The lid has my initials '{owner_initials}' engraved on it. "
            "I put a small black marker dot on the left earbud for identification. Owner: {owner}."
        ),
        found_desc=(
            "Found a white AirPods Pro charging case near the gymnasium entrance. "
            "Initials engraved on the lid. Both earbuds inside — left earbud has a small black marker dot. "
            "Found by {finder_fn}."
        ),
        proof_desc=(
            "The initials '{owner_initials}' on the case lid are mine — {owner}. "
            "The AirPods are paired to my iPhone and I can connect to them via Bluetooth immediately to prove ownership."
        ),
        reward="₱200",
    ),
    dict(
        category="Electronics", item_name="HP Pavilion 15 Laptop", brand="HP", color="Silver",
        location="College of Nursing Building",
        feature="'NURSING 3-B — {owner}' written in blue marker on underside near fan vents",
        lost_desc=(
            "Misplaced my silver HP Pavilion 15 laptop during our clinical simulation class. "
            "On the underside near the fan vents I wrote my name and section in blue marker: "
            "'NURSING 3-B — {owner}'. Laptop charger was also with it."
        ),
        found_desc=(
            "Found an HP Pavilion 15 laptop in the Nursing Building Room 201. "
            "Has 'NURSING 3-B — {owner}' written in blue marker on the bottom near the fan vents. "
            "No charger found with it. Left at the faculty room by {finder_fn}."
        ),
        proof_desc=(
            "The writing on the bottom reads 'NURSING 3-B — {owner}' which is my full name and section. "
            "I can provide the Windows product key sticker on the bottom and photos of the laptop before I lost it."
        ),
        reward="₱500",
    ),
    dict(
        category="Electronics", item_name="Sony WH-1000XM5 Headphones", brand="Sony", color="Black",
        location="Business School",
        feature="red ribbon tied on carrying-case zipper, small tear on right ear pad",
        lost_desc=(
            "Lost my black Sony WH-1000XM5 in its carrying case after a Business School presentation. "
            "The case has a small red ribbon I tied on the zipper for identification. "
            "Right ear pad has a tiny tear. Owner: {owner}."
        ),
        found_desc=(
            "Found a black Sony WH-1000XM5 headphone carrying case in the Business School conference room. "
            "Has a red ribbon on the zipper. Right ear cushion has a small tear. "
            "Left at the Student Affairs office by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner}. The red ribbon on the zipper is my identification mark — I tied it myself. "
            "The headphones are registered to my Sony account and I have the original receipt."
        ),
        reward="₱300",
    ),
    dict(
        category="Electronics", item_name="iPad Air 5th Generation", brand="Apple", color="Sky Blue",
        location="Arts & Sciences Hall",
        feature="transparent case with printed friend group photo tucked inside, Apple Pencil attached",
        lost_desc=(
            "Lost my Sky Blue iPad Air 5th gen during Fine Arts class at Arts & Sciences Hall. "
            "Has a transparent case with a printed photo of my friend group tucked behind the back panel. "
            "Apple Pencil was magnetically attached on the side. Owner: {owner}."
        ),
        found_desc=(
            "Found a Sky Blue iPad Air with a clear case in Arts & Sciences Hall Room 105. "
            "Has a printed photo of a group of students tucked inside the case. "
            "Apple Pencil on the side. Left at the faculty room by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner} and I appear in the photo tucked in the case. "
            "I can describe every person in the photo and I know the 6-digit iPad passcode and Apple ID linked to it."
        ),
        reward=None,
    ),
    dict(
        category="Electronics", item_name="Casio FX-991EX Scientific Calculator", brand="Casio", color="Black",
        location="Science Complex",
        feature="'{owner}' written in white correction fluid on back, small dent on lower-left corner",
        lost_desc=(
            "Lost my black Casio FX-991EX after our Physics long exam at the Science Complex. "
            "Has my name '{owner}' written in white correction fluid on the back. "
            "Small dent on the lower-left corner from when I dropped it once."
        ),
        found_desc=(
            "Found a Casio FX-991EX calculator in Science Complex Room 302 right after an exam. "
            "Has a name written in white on the back and a small dent on the lower-left corner. "
            "Left on the desk by {finder_fn}."
        ),
        proof_desc=(
            "My name '{owner}' is on the back in my handwriting. "
            "I can describe the exact shape of the dent and I have the original National Bookstore receipt."
        ),
        reward=None,
    ),
    dict(
        category="Electronics", item_name="Xiaomi Redmi Note 12 Pro", brand="Xiaomi", color="Midnight Black",
        location="IT Building",
        feature="green silicone case, cracked back glass on lower half",
        lost_desc=(
            "Lost my Xiaomi Redmi Note 12 Pro in the IT Building computer lab. "
            "Midnight black phone in a green silicone case. Back glass is cracked on the lower half. "
            "Has many apps installed for my programming subjects. Owner: {owner}."
        ),
        found_desc=(
            "Found a black Xiaomi phone with a green silicone case in IT Building Lab 3. "
            "Back glass is cracked on the lower half. Screen was locked when found by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner} and this is my phone. I know the PIN and pattern lock. "
            "The phone is signed into my Google account — I can demonstrate this on-site."
        ),
        reward=None,
    ),
    dict(
        category="Electronics", item_name="ASUS ROG Zephyrus G14 Laptop", brand="ASUS", color="Black",
        location="Dormitory 1 Lobby",
        feature="ROG logo RGB set to red-blue cycle, 'PROPERTY OF {owner}' asset tag on base",
        lost_desc=(
            "Left my black ASUS ROG Zephyrus G14 at the dorm lobby while I went to get food. "
            "Custom RGB on the ROG logo set to a red-blue cycle pattern. "
            "Has an asset tag on the base that reads 'PROPERTY OF {owner}'. Very urgent — thesis inside."
        ),
        found_desc=(
            "Found a black ASUS ROG gaming laptop in the Dormitory 1 lobby. "
            "ROG logo was still lit up in a red-blue cycle. "
            "Has an asset tag on the base with a name on it. Found by {finder_fn}, left at the guard desk."
        ),
        proof_desc=(
            "The asset tag reads 'PROPERTY OF {owner}' — that is my full name. "
            "I can provide the ASUS serial number and the laptop is linked to my ASUS account with the same name."
        ),
        reward="₱2,000",
    ),
    dict(
        category="Electronics", item_name="Canon EOS M50 Mark II Camera", brand="Canon", color="Black",
        location="Architecture Hall",
        feature="colorful woven camera strap, '{owner_fn}' written on lens cap in marker",
        lost_desc=(
            "Lost my black Canon EOS M50 Mark II during our Architecture campus documentation shoot. "
            "Has a colorful woven camera strap. The lens cap has my name '{owner_fn}' written on it in marker. "
            "Memory card with our class photos is still inside. Owner: {owner}."
        ),
        found_desc=(
            "Found a black Canon EOS M50 Mark II camera with a colorful woven strap near the Architecture Hall. "
            "Lens cap has a name written on it in marker. Memory card still inside. "
            "Found by {finder_fn}, left at the faculty room."
        ),
        proof_desc=(
            "My name '{owner_fn}' is written on the lens cap (full name: {owner}). "
            "The memory card contains photos of our Architecture class documentation — I can describe the subjects. "
            "I also have the camera serial number from the original box."
        ),
        reward="₱500",
    ),
    dict(
        category="Electronics", item_name="JBL Flip 6 Bluetooth Speaker", brand="JBL", color="Teal",
        location="Oval / Track",
        feature="white electrical tape with '{owner_initials}' written on one end, small dent on right side",
        lost_desc=(
            "Lost my teal JBL Flip 6 speaker after afternoon jogging at the oval. "
            "Has a strip of white electrical tape on one end with my initials '{owner_initials}' written on it. "
            "Small dent on the right side. Owner: {owner}."
        ),
        found_desc=(
            "Found a teal JBL Flip 6 near the oval track exit. "
            "Has white electrical tape on one end with initials written on it. Small dent on the right side. "
            "Found by {finder_fn}, still works."
        ),
        proof_desc=(
            "The initials '{owner_initials}' on the tape are mine — {owner}. "
            "I can pair the speaker to my phone via Bluetooth to prove ownership "
            "and I have the original JBL box with the serial number."
        ),
        reward=None,
    ),
    dict(
        category="Electronics", item_name="TI-84 Plus CE Graphing Calculator", brand="Texas Instruments", color="Black",
        location="Engineering Building",
        feature="purple protective case, '{owner}' scratched on back panel with pen tip",
        lost_desc=(
            "Lost my black TI-84 Plus CE graphing calculator after an Engineering Mathematics exam. "
            "Has a purple protective case. My name '{owner}' is scratched into the back panel with a pen tip."
        ),
        found_desc=(
            "Found a black TI-84 Plus CE in a purple case near the Engineering Building 2nd floor. "
            "Has a name scratched on the back of the calculator. "
            "Left at the faculty room by {finder_fn}."
        ),
        proof_desc=(
            "My name '{owner}' is scratched into the back of the calculator with my own pen. "
            "I can describe the exact scratch style and I have the National Bookstore purchase receipt."
        ),
        reward=None,
    ),

    # ── WALLETS & BAGS ───────────────────────────────────────────────────────
    dict(
        category="Wallets & Bags", item_name="Brown Leather Bifold Wallet", brand=None, color="Brown",
        location="Cafeteria",
        feature="contains student ID of {owner}, two BDO ATM cards, driver's license, approx. ₱850 cash",
        lost_desc=(
            "Lost my brown leather bifold wallet at the cafeteria during lunch. "
            "Contains my student ID ({owner}), two BDO ATM cards, driver's license, "
            "and approximately ₱850 cash. Very urgent, please return."
        ),
        found_desc=(
            "Found a brown leather bifold wallet near the cafeteria cashier counter. "
            "Contains a student ID with a name and photo, two ATM cards, a driver's license, and cash. "
            "Turned in to the guard station by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner} and the student ID inside has my photo and name. "
            "I can confirm the exact cash amount and provide the last 4 digits of both ATM card numbers."
        ),
        reward="₱200",
    ),
    dict(
        category="Wallets & Bags", item_name="Black JanSport Backpack", brand="JanSport", color="Black",
        location="Main Library",
        feature="blue keychain with '{owner_fn} 💙' on main zipper, blue inner lining",
        lost_desc=(
            "Left my black JanSport backpack at the Main Library 3rd floor study area. "
            "Has a blue keychain on the main zipper that says '{owner_fn} 💙' — my nickname. "
            "Blue inner lining. Contains my laptop, charger, engineering notebooks, and textbooks. Owner: {owner}."
        ),
        found_desc=(
            "Found a black JanSport backpack at the Main Library 3rd floor. "
            "Has a blue keychain on the main zipper with a name and heart emoji on it. "
            "Contents heavy and intact. Found by {finder_fn}."
        ),
        proof_desc=(
            "The keychain reads '{owner_fn} 💙' — {owner_fn} is my nickname, full name {owner}. "
            "The laptop inside is mine and I can unlock it on-site. "
            "My textbooks have my name written on the first page."
        ),
        reward="₱300",
    ),
    dict(
        category="Wallets & Bags", item_name="Red Leather Crossbody Bag", brand=None, color="Red",
        location="Administration Building",
        feature="gold chain strap, heart-shaped lock charm with {owner_fn}'s birthdate engraved on back",
        lost_desc=(
            "Lost my red leather crossbody bag with a gold chain strap near the Admin Building. "
            "Has a heart-shaped lock charm on the zipper with my birthdate engraved on the back. "
            "Owner: {owner}."
        ),
        found_desc=(
            "Found a red leather crossbody bag with a gold chain strap near the Admin Building entrance. "
            "Has a heart lock charm on the zipper with a date engraved on the back. "
            "Contents appear undisturbed. Found by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner}. The heart lock charm has my birthdate engraved on the back. "
            "I can describe the exact contents of the bag including a specific perfume brand inside."
        ),
        reward=None,
    ),
    dict(
        category="Wallets & Bags", item_name="Navy Blue Targus Laptop Bag", brand="Targus", color="Navy Blue",
        location="Engineering Building",
        feature="white name tag on handle: '{owner} — CE 201'",
        lost_desc=(
            "Lost my navy blue Targus laptop bag near the Engineering Building. "
            "Has a white name tag on the handle that reads '{owner} — CE 201'. "
            "Contains my laptop, USB hub, and rolled engineering drawings."
        ),
        found_desc=(
            "Found a navy blue Targus laptop bag in the Engineering Building parking area. "
            "Has a white name tag on the handle with a full name and section. "
            "Contains a laptop and rolled documents. Found by {finder_fn}."
        ),
        proof_desc=(
            "The name tag reads '{owner} — CE 201' — that is my full name and section. "
            "The engineering drawings inside have my name, student number, and professor's grading signature. "
            "I can describe them in detail."
        ),
        reward="₱500",
    ),
    dict(
        category="Wallets & Bags", item_name="Pink Mini Backpack with Ita Bag Window", brand=None, color="Pink",
        location="Arts & Sciences Hall",
        feature="clear window pocket with anime badge collection, '{owner_fn}' stitched on inner tag",
        lost_desc=(
            "Lost my pink mini backpack with a clear ita-bag window pocket full of my anime badge collection. "
            "Has my nickname '{owner_fn}' stitched on the inner fabric tag. "
            "These badges are irreplaceable — collected over several years. Owner: {owner}."
        ),
        found_desc=(
            "Found a pink mini backpack with a clear window pocket showing an anime badge collection "
            "near the Arts & Sciences Hall vending machines. "
            "Has a name stitched on the inner tag. Found by {finder_fn}."
        ),
        proof_desc=(
            "The inner tag reads '{owner_fn}' — my nickname (full name: {owner}). "
            "I can identify every single badge in the window pocket by name and series."
        ),
        reward=None,
    ),
    dict(
        category="Wallets & Bags", item_name="Black Fossil Leather Messenger Bag", brand="Fossil", color="Black",
        location="Business School",
        feature="brass buckle clasp, '{owner_initials}' monogram embossed near base",
        lost_desc=(
            "Lost my black Fossil leather messenger bag after my MBA seminar at the Business School. "
            "Has a brass buckle clasp and my monogram '{owner_initials}' embossed near the base. "
            "Contains my tablet and important business documents. Owner: {owner}."
        ),
        found_desc=(
            "Found a black Fossil leather messenger bag with a brass buckle clasp in the Business School. "
            "Has a monogram embossed near the base. "
            "Looks expensive. Found by {finder_fn}."
        ),
        proof_desc=(
            "The monogram '{owner_initials}' stands for my full name {owner}. "
            "I have the Fossil warranty card and can describe the exact documents inside the bag."
        ),
        reward="₱1,000",
    ),

    # ── KEYS ─────────────────────────────────────────────────────────────────
    dict(
        category="Keys", item_name="Toyota Vios Car Key with Remote Fob", brand="Toyota", color="Black",
        location="Cafeteria",
        feature="orange lanyard, Snoopy rubber keychain with small bite mark on left ear",
        lost_desc=(
            "Lost my Toyota Vios car key with remote fob at the cafeteria. "
            "Has an orange lanyard and a Snoopy rubber keychain. "
            "The Snoopy keychain has a small bite mark on the left ear. This is my only key. Owner: {owner}."
        ),
        found_desc=(
            "Found a Toyota car key fob with an orange lanyard and a Snoopy rubber keychain near a cafeteria table. "
            "Snoopy keychain has a small bite mark on one ear. "
            "Left at the Information Desk by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner}. The bite mark is on the left ear of the Snoopy keychain — I can describe it exactly. "
            "I can demonstrate the key opens my Toyota Vios and show the matching plate on my OR/CR."
        ),
        reward="₱500",
    ),
    dict(
        category="Keys", item_name="Dormitory Room Key Set", brand=None, color="Silver",
        location="Gymnasium",
        feature="3 keys on ring (dorm, padlock, mailbox), blue rubber tag with room number written on it",
        lost_desc=(
            "Lost my dormitory key set after basketball practice at the gymnasium. "
            "Three keys on one ring: main dorm door key, small padlock key, and tiny mailbox key. "
            "Has a blue rubber tag with my room number written on it. Owner: {owner}."
        ),
        found_desc=(
            "Found a key set with 3 keys near the gymnasium bleachers. "
            "Has a blue rubber tag with a room number written on it. "
            "Left at the dormitory front desk by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner}. The room number on the tag matches my dormitory room. "
            "The dormitory office can verify my room assignment using my student ID. "
            "I can also describe the padlock model the small key opens."
        ),
        reward=None,
    ),
    dict(
        category="Keys", item_name="Honda Click Motorcycle Key", brand="Honda", color="Black",
        location="Parking Lot A",
        feature="'{owner_fn}' laser-etched on key blade, Hello Kitty rubber keychain",
        lost_desc=(
            "Lost my Honda Click motorcycle key in Parking Lot A. "
            "Has my first name '{owner_fn}' laser-etched on the key blade. "
            "Hello Kitty rubber keychain attached. Owner: {owner}."
        ),
        found_desc=(
            "Found a Honda motorcycle key with a Hello Kitty rubber keychain in Parking Lot A. "
            "Has a name etched on the blade. "
            "Turned in to the security guard by {finder_fn}."
        ),
        proof_desc=(
            "My name '{owner_fn}' is etched on the blade (full name: {owner}). "
            "I can start my Honda Click motorcycle with this key and show the matching plate on my OR/CR."
        ),
        reward=None,
    ),
    dict(
        category="Keys", item_name="House Key Bundle with Red Tag", brand=None, color="Silver",
        location="Main Library",
        feature="5 keys on ring, red rubber tag labeled '{owner} RESIDENCE', mini-flashlight on ring",
        lost_desc=(
            "Left my house key bundle at a library study cubicle. "
            "Five keys on one ring with a red rubber tag that says '{owner} RESIDENCE' in marker. "
            "Has a small mini-flashlight attached to the ring."
        ),
        found_desc=(
            "Found a bundle of 5 house keys with a red rubber tag near the library study area. "
            "The tag has a name and the word RESIDENCE written in marker. Has a mini-flashlight on the ring. "
            "Found by {finder_fn}."
        ),
        proof_desc=(
            "The tag reads '{owner} RESIDENCE' — {owner} is my surname. "
            "I can describe the shape and brand of each key and provide my home address matching the tag."
        ),
        reward=None,
    ),

    # ── CLOTHING ─────────────────────────────────────────────────────────────
    dict(
        category="Clothing", item_name="Gray UP Diliman Hoodie", brand=None, color="Gray",
        location="Main Library",
        feature="'{owner}' stitched inside collar, small blue ink stain on front kangaroo pocket",
        lost_desc=(
            "Lost my gray UP Diliman hoodie at the Main Library during finals week. "
            "Has my name '{owner}' stitched inside the collar by my mother. "
            "Small blue ink stain on the front kangaroo pocket."
        ),
        found_desc=(
            "Found a gray UP Diliman hoodie near the Main Library lounge area. "
            "Has a name stitched inside the collar and a small ink stain on the front pocket. "
            "Left at the Student Affairs office by {finder_fn}."
        ),
        proof_desc=(
            "The stitching inside reads '{owner}' — my full name. "
            "I can describe exactly what was inside the front pocket when I lost it: a folded exam reviewer."
        ),
        reward=None,
    ),
    dict(
        category="Clothing", item_name="White Nursing Laboratory Gown", brand=None, color="White",
        location="College of Nursing Building",
        feature="'{owner} — NURSING' embroidered in blue thread on left chest pocket, missing top button",
        lost_desc=(
            "Lost my white nursing lab gown after our clinical skills class at the Nursing Building. "
            "Has '{owner} — NURSING' embroidered in blue thread on the left chest pocket. "
            "Top button is missing — I never replaced it."
        ),
        found_desc=(
            "Found a white lab gown in the Nursing Building locker area. "
            "Has a student's full name and program embroidered on the chest pocket in blue thread. "
            "Top button is missing. Found by {finder_fn}."
        ),
        proof_desc=(
            "The embroidery reads '{owner} — NURSING' which is my name. "
            "I can show my student ID and clinical schedule matching the lab date. "
            "The missing top button is a detail only the owner would mention."
        ),
        reward=None,
    ),
    dict(
        category="Clothing", item_name="Maroon Varsity Basketball Jacket", brand=None, color="Maroon",
        location="Gymnasium",
        feature="'{owner} #{jersey_no}' printed on back, tournament patches on right sleeve",
        lost_desc=(
            "Left my maroon varsity basketball jacket at the gymnasium after practice. "
            "Has my name '{owner} #{jersey_no}' printed on the back. "
            "The right sleeve has tournament patches from competitions we won this year."
        ),
        found_desc=(
            "Found a maroon varsity basketball jacket near the gymnasium exit. "
            "Has a player name and jersey number printed on the back. Several tournament patches on the right sleeve. "
            "Found by {finder_fn}."
        ),
        proof_desc=(
            "The jacket reads '{owner} #{jersey_no}' — I am {owner}, jersey number {jersey_no}. "
            "I can name every tournament patch on the sleeve and the year each was won. "
            "My coach can also verify my identity."
        ),
        reward=None,
    ),
    dict(
        category="Clothing", item_name="Blue Levi's Denim Jacket", brand="Levi's", color="Blue",
        location="Arts & Sciences Hall",
        feature="hand-painted flowers on back by owner, '{owner}' name tag inside collar",
        lost_desc=(
            "Lost my blue Levi's denim jacket after Fine Arts class at Arts & Sciences Hall. "
            "The back has hand-painted flowers that I painted myself — completely unique. "
            "Has a name tag stitched inside the collar: '{owner}'."
        ),
        found_desc=(
            "Found a blue Levi's denim jacket with beautiful hand-painted flowers on the back at the cafeteria. "
            "Has a name tag stitched inside the collar. "
            "Left at the guard station by {finder_fn}."
        ),
        proof_desc=(
            "I painted those flowers myself and have photos of the process on my phone. "
            "The name tag inside reads '{owner}' which is my name."
        ),
        reward=None,
    ),

    # ── JEWELRY ──────────────────────────────────────────────────────────────
    dict(
        category="Jewelry", item_name="Gold Necklace with Cross Pendant", brand=None, color="Gold",
        location="Chapel",
        feature="18k gold chain, 'From Lola Caring — {owner}' engraved on back of cross",
        lost_desc=(
            "Lost my gold necklace with a cross pendant near the school chapel. "
            "The back of the cross is engraved 'From Lola Caring — {owner}' — a gift from my late grandmother. "
            "Extremely sentimental. Reward offered. Owner: {owner}."
        ),
        found_desc=(
            "Found a gold necklace with a cross pendant near the Chapel pews. "
            "There is an engraving on the back of the cross pendant. "
            "Brought to the Admin Office immediately by {finder_fn}."
        ),
        proof_desc=(
            "The engraving reads 'From Lola Caring — {owner}' — that is my name. "
            "Lola Caring is my late grandmother Rosario. "
            "I have photos of me wearing this necklace at her birthday."
        ),
        reward="₱1,000",
    ),
    dict(
        category="Jewelry", item_name="Silver Bracelet with Name Engraving", brand=None, color="Silver",
        location="Cafeteria",
        feature="sterling silver plate with '{owner_fn}' engraved in cursive, small star charm",
        lost_desc=(
            "Lost my silver bracelet at the cafeteria. "
            "Has my name '{owner_fn}' engraved in cursive on the plate and a small star charm. "
            "Birthday gift from a loved one. Owner: {owner}."
        ),
        found_desc=(
            "Found a silver bracelet with a name engraved in cursive on it near the cafeteria fountain. "
            "Has a small star charm attached. "
            "Found by {finder_fn}."
        ),
        proof_desc=(
            "The name engraved is '{owner_fn}' — my first name (full: {owner}). "
            "The star charm has a small scratch on one point from when I dropped it. "
            "I have a birthday photo of me wearing this bracelet."
        ),
        reward=None,
    ),
    dict(
        category="Jewelry", item_name="Seiko 5 Automatic Watch", brand="Seiko", color="Silver",
        location="Engineering Building",
        feature="blue dial, stainless steel bracelet, caseback engraved '{owner_initials} — {grad_date}'",
        lost_desc=(
            "Lost my Seiko 5 automatic watch with a blue dial near the Engineering Building. "
            "Has a stainless steel bracelet and the caseback is engraved with my initials and graduation date: "
            "'{owner_initials} — {grad_date}'."
        ),
        found_desc=(
            "Found a Seiko 5 watch with a blue dial near the Engineering Building 2nd floor staircase. "
            "Has engraving on the caseback. "
            "Left with the building security by {finder_fn}."
        ),
        proof_desc=(
            "The caseback reads '{owner_initials} — {grad_date}' — my initials are {owner_initials} (full name: {owner}). "
            "{grad_date} is my graduation date. I have the original Seiko warranty card."
        ),
        reward="₱500",
    ),
    dict(
        category="Jewelry", item_name="Freshwater Pearl Stud Earrings", brand=None, color="White",
        location="Administration Building",
        feature="pearl studs, right earring back is gold-toned, left is silver-toned (intentionally mismatched)",
        lost_desc=(
            "Lost a pair of freshwater pearl stud earrings at the Admin Building while processing documents. "
            "The identifying detail: the right earring back is gold-toned and the left is silver — "
            "they became mismatched after I lost one back and replaced it. Owner: {owner}."
        ),
        found_desc=(
            "Found a pair of white pearl stud earrings near the registrar's window. "
            "Noticed the earring backs are mismatched — one gold-toned, one silver-toned. "
            "Turned in to the Admin Office by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner}. Only I would know the backs are mismatched — "
            "I replaced a lost back with one from a different pair. "
            "These earrings were my Confirmation gift in 2017."
        ),
        reward=None,
    ),

    # ── DOCUMENTS ────────────────────────────────────────────────────────────
    dict(
        category="Documents", item_name="Student ID Card", brand=None, color=None,
        location="Cafeteria",
        feature="photo ID of {owner}, enrolled in {course}",
        lost_desc=(
            "Lost my student ID at the cafeteria. "
            "Name: {owner}, enrolled in {course}. "
            "Desperately need it for my thesis defense next week."
        ),
        found_desc=(
            "Found a student ID card on the cafeteria floor. "
            "Name on the card is {owner}, enrolled in {course}. "
            "Turned in to the guard station by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner}. The ID has my photo and name. "
            "I can present myself in person with a secondary government ID to claim it."
        ),
        reward=None,
    ),
    dict(
        category="Documents", item_name="Brown Envelope with Academic Documents", brand=None, color="Brown",
        location="Administration Building",
        feature="envelope labeled '{owner}', contains TOR, diploma copy, birth certificate",
        lost_desc=(
            "Lost a brown envelope labeled '{owner}' near the Admin Building. "
            "Contains my Transcript of Records, certified diploma copy, and birth certificate. "
            "Urgently needed for a job application."
        ),
        found_desc=(
            "Found a brown envelope with a name written on it near the Admin Building entrance. "
            "Did not open it but it contains what feels like important documents. "
            "Handed to the admin staff by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner} and the envelope is labeled with my name. "
            "The TOR inside shows my grades which I can recite in detail. "
            "I can provide a copy of my diploma for cross-reference."
        ),
        reward="₱500",
    ),
    dict(
        category="Documents", item_name="Blue Plastic Folder with Scholarship Requirements", brand=None, color="Blue",
        location="Medicine Building",
        feature="'{owner}' name sticker on cover, contains medical cert, enrollment form, scholarship papers",
        lost_desc=(
            "Lost my blue plastic folder at the Medicine Building. "
            "Has a '{owner}' name sticker on the cover. "
            "Contains my signed medical certificate, enrollment form, and scholarship renewal papers. Very urgent."
        ),
        found_desc=(
            "Found a blue plastic folder with a name sticker on the cover near the Medicine Building corridor. "
            "Looks like it contains medical and school documents. "
            "Left at the nursing faculty room by {finder_fn}."
        ),
        proof_desc=(
            "The name sticker reads '{owner}' — my name. "
            "The scholarship documents inside have my scholar ID number and my grantor's name, which I can provide. "
            "The medical certificate is signed by Dr. Reyes at the university clinic."
        ),
        reward=None,
    ),

    # ── OTHER ────────────────────────────────────────────────────────────────
    dict(
        category="Other", item_name="Black Prescription Eyeglasses", brand=None, color="Black",
        location="Main Library",
        feature="black rectangular frame, clear tape on left temple, Rx -3.00 / -3.25",
        lost_desc=(
            "Lost my black prescription eyeglasses at the Main Library. "
            "Black rectangular frame, left temple has clear tape where I repaired a crack. "
            "Prescription is -3.00 right / -3.25 left. Cannot see without them. Owner: {owner}."
        ),
        found_desc=(
            "Found a pair of black rectangular eyeglasses on the 2nd floor of the Main Library. "
            "Left temple has clear tape on it. Folded neatly on a table. "
            "Found by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner}. The tape on the left temple was applied by me after I sat on the glasses. "
            "I have my optical shop prescription receipt showing the exact -3.00 / -3.25 Rx."
        ),
        reward=None,
    ),
    dict(
        category="Other", item_name="Pacific Blue Hydro Flask 32oz Water Bottle", brand="Hydro Flask", color="Pacific Blue",
        location="Gymnasium",
        feature="plant stickers on body, '{owner_fn}' written in permanent marker on bottom",
        lost_desc=(
            "Lost my Pacific Blue Hydro Flask 32oz after PE class at the gymnasium. "
            "Has plant-themed stickers on the body and my name '{owner_fn}' written in permanent marker on the bottom. "
            "Owner: {owner}."
        ),
        found_desc=(
            "Found a Pacific Blue Hydro Flask with plant stickers near the gymnasium exit. "
            "Has a first name written in marker on the bottom. "
            "Left at the Student Affairs office by {finder_fn}."
        ),
        proof_desc=(
            "My name '{owner_fn}' is on the bottom in my handwriting (full name: {owner}). "
            "I can identify each sticker on the bottle and describe exactly where each one is placed."
        ),
        reward=None,
    ),
    dict(
        category="Other", item_name="Littmann Classic III Stethoscope", brand="Littmann", color="Navy Blue",
        location="College of Nursing Building",
        feature="'{owner} RN' name tag on diaphragm side, navy blue tubing",
        lost_desc=(
            "Lost my Littmann Classic III stethoscope at the Nursing Building. "
            "Navy blue tubing with a name tag on the diaphragm side that reads '{owner} RN'. "
            "Urgently needed for my clinical rotation tomorrow."
        ),
        found_desc=(
            "Found a navy blue Littmann stethoscope near the Nursing Building simulation room. "
            "Has a name tag on the diaphragm side that reads '{owner} RN'. "
            "Placed in the faculty office by {finder_fn}."
        ),
        proof_desc=(
            "The name tag reads '{owner} RN' — that is my full name. "
            "I can provide the Littmann serial number from the original packaging and the purchase receipt."
        ),
        reward="₱500",
    ),
    dict(
        category="Other", item_name="White Fujifilm Instax Mini 11 Camera", brand="Fujifilm", color="White",
        location="Arts & Sciences Hall",
        feature="unique washi tape pattern applied by {owner_fn}, film counter shows shots remaining",
        lost_desc=(
            "Lost my white Fujifilm Instax Mini 11 camera during a Fine Arts event at Arts & Sciences Hall. "
            "White base covered in my own washi tape design — completely unique pattern. "
            "Film inside still has shots remaining. Owner: {owner}."
        ),
        found_desc=(
            "Found a white Fujifilm Instax camera covered in washi tape near the Arts & Sciences Hall entrance. "
            "Film counter shows shots remaining. "
            "Found by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner} ({owner_fn}) and I applied the washi tape myself in a specific design I can describe in detail. "
            "I have Instagram posts of this camera before I lost it showing the exact pattern."
        ),
        reward=None,
    ),
    dict(
        category="Other", item_name="Black Compact Umbrella with Cat Print", brand=None, color="Black",
        location="Main Library",
        feature="cat face pattern on canopy, orange handle, '{owner}' written on wrist strap in fabric marker",
        lost_desc=(
            "Lost my black compact umbrella with a cat face pattern on the canopy near the Main Library. "
            "Has an orange handle. My name '{owner}' is written on the wrist strap in fabric marker."
        ),
        found_desc=(
            "Found a black compact umbrella with a cat face canopy pattern near the Main Library entrance. "
            "Orange handle, has a name written on the wrist strap in marker. "
            "Found by {finder_fn}."
        ),
        proof_desc=(
            "My name '{owner}' is on the wrist strap in my handwriting. "
            "The cat pattern has a small fading spot on one panel from sun exposure that I can describe precisely."
        ),
        reward=None,
    ),
    dict(
        category="Other", item_name="Yonex Astrox 88S Badminton Racket", brand="Yonex", color="Black/Gold",
        location="Gymnasium",
        feature="red custom grip tape, '{owner}' written on shaft in white marker",
        lost_desc=(
            "Lost my Yonex Astrox 88S badminton racket after PE class at the gymnasium. "
            "Black and gold colorway with red custom grip tape I applied myself. "
            "My name '{owner}' is written on the shaft in white marker."
        ),
        found_desc=(
            "Found a Yonex badminton racket with red grip tape near the gymnasium equipment room. "
            "Has a name written in white marker on the shaft. "
            "Found by {finder_fn}."
        ),
        proof_desc=(
            "My name '{owner}' is on the shaft. "
            "I have tournament photos from last month holding this exact racket. "
            "String tension is set to 24 lbs which can be verified."
        ),
        reward=None,
    ),

    # ── SPORTS ───────────────────────────────────────────────────────────────
    dict(
        category="Sports", item_name="White/Blue Nike Air Max Running Shoes", brand="Nike", color="White/Blue",
        location="Gymnasium",
        feature="size 9, '{owner}' written inside both shoe tongues in permanent marker",
        lost_desc=(
            "Lost my white and blue Nike Air Max running shoes (size 9) at the gymnasium locker room after PE. "
            "Has my name '{owner}' written inside both shoe tongues in permanent marker."
        ),
        found_desc=(
            "Found a pair of white and blue Nike Air Max shoes (size 9) near the gymnasium locker room. "
            "A name is written inside the tongues of both shoes. "
            "Found by {finder_fn}."
        ),
        proof_desc=(
            "The name inside the tongues is '{owner}' — my name. "
            "The shoes have a specific scuff mark on the left outer sole that I can describe precisely. "
            "I have the original Nike box."
        ),
        reward=None,
    ),
    dict(
        category="Sports", item_name="Speedo Vanquisher 2.0 Swimming Goggles", brand="Speedo", color="Blue",
        location="Swimming Pool Area",
        feature="blue tinted prescription lenses Rx -2.50, '{owner_fn}' written on strap",
        lost_desc=(
            "Lost my Speedo Vanquisher 2.0 goggles at the swimming pool. "
            "Blue tinted lenses with prescription inserts (-2.50 Rx). "
            "My name '{owner_fn}' is written on the strap in marker. Owner: {owner}."
        ),
        found_desc=(
            "Found a pair of blue Speedo swimming goggles near the pool equipment shelf. "
            "A name is written on the strap. The lenses appear to be prescription. "
            "Found by {finder_fn}."
        ),
        proof_desc=(
            "The strap has '{owner_fn}' written on it — my first name (full name: {owner}). "
            "The goggles have -2.50 prescription inserts matching my eye grade, which I can prove with my optometrist's prescription."
        ),
        reward=None,
    ),

    # ── PETS ─────────────────────────────────────────────────────────────────
    dict(
        category="Pets", item_name="Orange Tabby Cat (Missing)", brand=None, color="Orange",
        location="Research Center",
        feature="white chest patch, blue collar with bell and tag 'KIKO — {owner_fn}'",
        lost_desc=(
            "Our campus cat Kiko is missing near the Research Center. "
            "Orange tabby with a distinctive white chest patch. "
            "Wearing a blue collar with a bell and a name tag that reads 'KIKO — {owner_fn}'. "
            "Very friendly — responds to his name. Owner: {owner}."
        ),
        found_desc=(
            "Found an orange tabby cat with a white chest patch near the Graduate School Building. "
            "Wearing a blue collar with a bell and a name tag. Very friendly and healthy-looking. "
            "Brought to the Student Affairs office by {finder_fn}."
        ),
        proof_desc=(
            "I am {owner} ('{owner_fn}'). The tag reads 'KIKO — {owner_fn}'. "
            "I can describe Kiko's markings including a small notch on his left ear from an old scratch. "
            "I have hundreds of photos of him on my phone."
        ),
        reward=None,
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
#  SOLO REPORT TEMPLATES  (no matching counterpart — standalone reports)
# ─────────────────────────────────────────────────────────────────────────────
SOLO_TEMPLATES = [
    dict(cat="Electronics",    rt="lost",  item="Google Pixel 7 Pro",           brand="Google",           color="Obsidian",
         loc="IT Building",       detail="3rd floor corridor",
         desc="Lost my Google Pixel 7 Pro after a night class. Has a clear case with a BTS photo card inside. Owner: {owner}.",
         reward="₱300"),
    dict(cat="Electronics",    rt="found", item="Wired Earphones in Fabric Pouch", brand=None,            color="White",
         loc="Main Library",      detail=None,
         desc="Found a pair of wired earphones with a small fabric pouch near the library entrance. Left at the guard station by {finder_fn}.",
         reward=None),
    dict(cat="Electronics",    rt="lost",  item="Keychron K2 Mechanical Keyboard", brand="Keychron",     color="Gray",
         loc="IT Building",       detail="CS Lab Room 401",
         desc="Lost my Keychron K2 TKL mechanical keyboard after staying late in the CS lab. Gray, has custom blue WASD keycaps. Owner: {owner}.",
         reward=None),
    dict(cat="Electronics",    rt="lost",  item="Seagate 1TB Portable Hard Drive", brand="Seagate",      color="Black",
         loc="Main Library",      detail="Study area near window",
         desc="Lost my Seagate 1TB portable hard drive. Black, has a red sticker on one side. Contains all my thesis files. Owner: {owner}.",
         reward="₱500"),
    dict(cat="Electronics",    rt="found", item="SanDisk 64GB Flash Drive",         brand="SanDisk",      color="Blue",
         loc="Administration Building", detail=None,
         desc="Found a SanDisk 64GB USB flash drive with a keychain ring near the photocopying center. Left at the admin desk by {finder_fn}.",
         reward=None),
    dict(cat="Electronics",    rt="lost",  item="Wacom Drawing Tablet (Small)",     brand="Wacom",        color="Black",
         loc="Arts & Sciences Hall", detail="Room 105",
         desc="Lost my small Wacom drawing tablet during Art class. Black, comes with a stylus. Owner: {owner}.",
         reward=None),
    dict(cat="Electronics",    rt="found", item="Anker 10000mAh Power Bank",        brand="Anker",        color="Black",
         loc="Oval / Track",      detail=None,
         desc="Found a black Anker power bank on a bench near the oval. Fully charged when found. Left at Student Affairs by {finder_fn}.",
         reward=None),
    dict(cat="Wallets & Bags", rt="lost",  item="Green Canvas Tote Bag",            brand=None,           color="Green",
         loc="Main Library",      detail="Ground floor reading area",
         desc="Lost a green canvas tote bag printed with 'READ MORE BOOKS'. Contains paperback novels, a notebook, and reusable utensils. Owner: {owner}.",
         reward=None),
    dict(cat="Wallets & Bags", rt="found", item="Black Velcro Wallet",              brand=None,           color="Black",
         loc="Gymnasium",         detail=None,
         desc="Found a small black velcro wallet near the gymnasium bleachers. Contains cash and what looks like a student ID. Turned in to security by {finder_fn}.",
         reward=None),
    dict(cat="Wallets & Bags", rt="lost",  item="Burgundy Leather Planner-Wallet", brand=None,           color="Burgundy",
         loc="Business School",   detail="3rd floor classroom hallway",
         desc="Lost a burgundy leather planner-wallet with weekly inserts and business card slots. My name is written inside the cover. Owner: {owner}.",
         reward=None),
    dict(cat="Wallets & Bags", rt="found", item="Gray Drawstring Gym Bag",          brand=None,           color="Gray",
         loc="Gymnasium",         detail=None,
         desc="Found a gray drawstring bag near the gymnasium locker room. Has gym clothes and a deodorant inside. Found by {finder_fn}.",
         reward=None),
    dict(cat="Keys",           rt="found", item="Key with Yellow Rubber Duck Keychain", brand=None,       color="Yellow",
         loc="Cafeteria",         detail=None,
         desc="Found a single key with a yellow rubber duck keychain in the cafeteria. Looks like a house or room key. Left at the information desk by {finder_fn}.",
         reward=None),
    dict(cat="Keys",           rt="lost",  item="Gym Locker Padlock Key",           brand=None,           color="Silver",
         loc="Gymnasium",         detail="Locker room area",
         desc="Lost the key to my gym locker padlock. Small silver key, has a tiny green dot painted on the head. Locker number 47. Owner: {owner}.",
         reward=None),
    dict(cat="Keys",           rt="found", item="Mitsubishi Car Key with Remote Fob", brand="Mitsubishi", color="Black",
         loc="Parking Lot A",     detail=None,
         desc="Found a Mitsubishi car key fob with a simple keyring near Parking Lot A. Turned in to the security guard by {finder_fn}.",
         reward=None),
    dict(cat="Clothing",       rt="lost",  item="Black PE Uniform Shirt",           brand=None,           color="Black",
         loc="Gymnasium",         detail="Male locker room",
         desc="Lost my official black PE uniform shirt. Has my student number printed on the back per school requirement. Medium size. Owner: {owner}.",
         reward=None),
    dict(cat="Clothing",       rt="found", item="Yellow Rain Jacket",               brand=None,           color="Yellow",
         loc="Administration Building", detail=None,
         desc="Found a yellow rain jacket hanging on a chair near the covered walkway. Unisex size M. No name tag inside. Found by {finder_fn}.",
         reward=None),
    dict(cat="Clothing",       rt="lost",  item="Green Nursing Scrubs Set",         brand=None,           color="Green",
         loc="College of Nursing Building", detail="Changing room",
         desc="Lost my green nursing scrubs (top and bottom) in the Nursing Building changing area. Has my last name written on the inner waistband. Owner: {owner}.",
         reward=None),
    dict(cat="Clothing",       rt="found", item="Black Sports Cap",                 brand=None,           color="Black",
         loc="Oval / Track",      detail=None,
         desc="Found a black sports cap near the oval track. Has a small embroidered logo on the front. No name inside. Found by {finder_fn}.",
         reward=None),
    dict(cat="Jewelry",        rt="lost",  item="Black Rubber Bracelet with Silver Studs", brand=None,    color="Black",
         loc="Covered Court",     detail="Basketball court sideline",
         desc="Lost my black rubber bracelet with silver stud accents at the Covered Court. Has a slight discoloration on the inner side from wear. Owner: {owner}.",
         reward=None),
    dict(cat="Jewelry",        rt="found", item="Plain Gold Band Ring",             brand=None,           color="Gold",
         loc="Chapel",            detail=None,
         desc="Found a plain gold band ring near the Chapel. No visible engravings. Turned in to the Administration Building by {finder_fn}.",
         reward=None),
    dict(cat="Jewelry",        rt="lost",  item="Handmade Beaded Friendship Bracelet", brand=None,        color="Multicolor",
         loc="Cafeteria",         detail="Near the exit",
         desc="Lost a handmade beaded bracelet spelling 'BESTIE' in red, blue, and white beads. Made by my best friend — irreplaceable. Owner: {owner}.",
         reward=None),
    dict(cat="Documents",      rt="found", item="UMID Card",                        brand=None,           color=None,
         loc="Administration Building", detail=None,
         desc="Found a laminated UMID card near the registrar's window. Has a photo of the owner. Turned in to the admin office by {finder_fn}.",
         reward=None),
    dict(cat="Documents",      rt="lost",  item="Yellow Folder with Thesis Proposal", brand=None,         color="Yellow",
         loc="Graduate School Building", detail="Research room 3",
         desc="Lost a yellow plastic folder containing my thesis proposal, concept paper, and data sheets. Has my name on the cover page. Owner: {owner}.",
         reward="₱300"),
    dict(cat="Documents",      rt="lost",  item="Philippine Passport",              brand=None,           color=None,
         loc="Administration Building", detail="International office lobby",
         desc="Lost my Philippine passport during the international student orientation. Maroon cover. Critical document — please return immediately. Owner: {owner}.",
         reward="₱1,000"),
    dict(cat="Other",          rt="found", item="Blue Insulated Lunch Box",         brand=None,           color="Blue",
         loc="Cafeteria",         detail=None,
         desc="Found a blue insulated lunch box near the cafeteria with food still inside. Has a cartoon bear sticker. Left at the cafeteria counter by {finder_fn}.",
         reward=None),
    dict(cat="Other",          rt="lost",  item="Blue Mini Cruiser Skateboard",     brand=None,           color="Blue",
         loc="Covered Court",     detail="Beside the bleachers",
         desc="Lost my blue mini cruiser skateboard near the Covered Court. Has custom orange wheels and a planet sticker on the bottom deck. Owner: {owner}.",
         reward=None),
    dict(cat="Other",          rt="lost",  item="Clarinet in Black Hard Case",      brand=None,           color="Black",
         loc="Arts & Sciences Hall", detail="Room 210 corridor",
         desc="Lost my clarinet in its black hard case after Music Theory class. Has a 'BAND 2021' sticker on the case and my initials engraved on the bell. Owner: {owner}.",
         reward="₱500"),
    dict(cat="Other",          rt="found", item="White Plastic Bag with Gym Clothes", brand=None,         color="White",
         loc="Gymnasium",         detail=None,
         desc="Found a white plastic bag with clean gym clothes (shorts and shirt) near the gymnasium exit. Found by {finder_fn}.",
         reward=None),
    dict(cat="Other",          rt="lost",  item="A2 Wooden Drawing Board",          brand=None,           color="Brown",
         loc="Architecture Hall", detail="Studio room 3",
         desc="Lost my A2 wooden drawing board after Architecture studio class. Has my student number written on the back in black marker. Very large and distinctive. Owner: {owner}.",
         reward=None),
    dict(cat="Other",          rt="found", item="Plain Black Backpack (No ID Found)", brand=None,         color="Black",
         loc="Administration Building", detail="Main gate area",
         desc="Found a plain black backpack near the main gate. Contains a towel, snacks, and a water bottle. No identification inside. At the security office. Found by {finder_fn}.",
         reward=None),
    dict(cat="Other",          rt="lost",  item="Spalding Size 7 Basketball",       brand="Spalding",     color="Orange",
         loc="Gymnasium",         detail="Basketball court",
         desc="Lost my Spalding size 7 basketball. Has my jersey number '9' in marker and specific scuff marks I can identify. Lost during afternoon free practice. Owner: {owner}.",
         reward=None),
    dict(cat="Other",          rt="lost",  item="Red First Aid Pouch",              brand=None,           color="Red",
         loc="College of Nursing Building", detail="Outreach preparation room",
         desc="Lost my red first aid kit pouch after our community health outreach. Has my name on the zipper tag. Contains medications — please do not open. Owner: {owner}.",
         reward=None),
    dict(cat="Other",          rt="found", item="Rolled Architecture Layout Print", brand=None,           color=None,
         loc="Administration Building", detail="Near printing shop",
         desc="Found a rolled large-format architecture layout print near the printing shop. Has a student name on the title block. Left at the admin desk by {finder_fn}.",
         reward=None),
]


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def rdatetime(days_back_min=1, days_back_max=180):
    delta = random.randint(days_back_min * 60, days_back_max * 24 * 60)
    return timezone.now() - timedelta(minutes=delta)

def rdate(days_back_max=120):
    return (timezone.now() - timedelta(days=random.randint(1, days_back_max))).date()

def rtime_val():
    return dtime(random.randint(7, 21), random.choice([0, 15, 30, 45]))

def pick(lst):   return random.choice(lst)
def maybe(v, p=0.5): return v if random.random() < p else None
def rip():       return f"192.168.{random.randint(0,255)}.{random.randint(1,254)}"
def rphone():    return f"+639{random.randint(100000000,999999999)}"
def rstudno():   return f"{random.randint(2018,2023)}-{random.randint(10000,99999)}"
def rgrad_date():
    return f"{random.randint(1,12):02d}.{random.randint(1,28):02d}.{random.randint(2020,2025)}"

def initials(fn, ln):
    parts = [fn] + ln.split()
    return ".".join(p[0].upper() for p in parts if p) + "."

def fill(template, owner=None, finder=None):
    """Resolve {placeholders} using real User objects."""
    if template is None:
        return ""
    d = {}
    if owner:
        fn, ln = owner.first_name, owner.last_name
        d.update({
            "owner":          f"{fn} {ln}",
            "owner_fn":       fn,
            "owner_initials": initials(fn, ln),
            "owner_un":       owner.username,
            "course":         pick(COURSES),
            "grad_date":      rgrad_date(),
            "jersey_no":      str(random.randint(1, 22)),
        })
    if finder:
        d["finder_fn"] = finder.first_name
        d["finder"]    = f"{finder.first_name} {finder.last_name}"
    try:
        return template.format(**d)
    except KeyError:
        return template


# ─────────────────────────────────────────────────────────────────────────────
#  COMMAND
# ─────────────────────────────────────────────────────────────────────────────
class Command(BaseCommand):
    help = "Seed the Findify database with realistic, coherent test data."

    def add_arguments(self, parser):
        parser.add_argument("--force",  action="store_true")
        parser.add_argument("--users",  type=int, default=40)
        parser.add_argument("--pairs",  type=int, default=len(PAIR_TEMPLATES))
        parser.add_argument("--solo",   type=int, default=len(SOLO_TEMPLATES))

    def handle(self, *args, **options):
        from api.models import (
            User, UserProfile, LostReport, ReportImage,
            MatchSuggestion, ClaimRequest, Notification, AuditLog,
        )

        # ── wipe ──────────────────────────────────────────────────────────────
        if options["force"]:
            self.stdout.write("  Wiping existing data…")
            for m in [AuditLog, Notification, ClaimRequest,
                      MatchSuggestion, ReportImage, LostReport, UserProfile]:
                m.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write(self.style.SUCCESS("  ✓ Cleared\n"))

        if not options["force"] and User.objects.filter(is_superuser=False).exists():
            self.stdout.write(self.style.WARNING(
                "Data already exists. Run with --force to reseed.\n"))
            return

        n_users = options["users"]
        n_pairs = min(options["pairs"], len(PAIR_TEMPLATES))
        n_solo  = min(options["solo"],  len(SOLO_TEMPLATES))

        # ── 1. ADMIN ────────────────────────────────────────────────────────────
        self.stdout.write("Creating admin…")
        admin, _ = User.objects.get_or_create(username="admin")
        admin.email = "admin@findify.edu"; admin.first_name = "Admin"; admin.last_name = "User"
        admin.role = "ADMIN"; admin.status = "active"; admin.is_staff = True
        admin.set_password("admin123"); admin.save()
        UserProfile.objects.get_or_create(user=admin)
        self.stdout.write(self.style.SUCCESS("  ✓ admin / admin123"))

        # ── 2. USERS ────────────────────────────────────────────────────────────
        self.stdout.write(f"Creating {n_users} users…")
        users      = []
        used_unames = set()
        sp = ["active"] * 80 + ["inactive"] * 12 + ["banned"] * 8
        bios = [
            "Engineering student — always losing my calculator.",
            "Nursing student. I report everything I find on campus.",
            "CS major. If I find it I post it here.",
            "Architecture student. Forever leaving things in the studio.",
            "Medical student. Very forgetful but very honest.",
            "Business student. Let's keep the campus clean.",
            "Fine Arts major. I care about the community.",
            "Graduate student. Happy to help return lost items.",
            None, None, None,
        ]
        for _ in range(n_users):
            fn  = pick(FIRST_NAMES);  ln  = pick(LAST_NAMES)
            base = f"{fn.lower()}.{ln.lower().replace(' ','').replace('.','')}"
            un = base; sfx = 2
            while un in used_unames: un = f"{base}{sfx}"; sfx += 1
            used_unames.add(un)
            u = User.objects.create_user(
                username=un, email=f"{un}@student.findify.edu",
                password="password123", first_name=fn, last_name=ln,
                role="USER", status=pick(sp),
            )
            u.date_joined = rdatetime(days_back_max=400)
            u.save(update_fields=["date_joined"])
            UserProfile.objects.get_or_create(user=u, defaults=dict(
                phone_number=maybe(rphone(), 0.55),
                bio=maybe(pick(bios), 0.45),
            ))
            users.append(u)
        self.stdout.write(self.style.SUCCESS(f"  ✓ {n_users} users"))

        # ── 3. MATCHED PAIRS ────────────────────────────────────────────────────
        self.stdout.write(f"Creating {n_pairs} matched pairs…")

        outcomes = (
            ["confirmed_matched"]  * 25 +
            ["confirmed_claimed"]  * 15 +
            ["confirmed_closed"]   * 10 +
            ["pending_suggestion"] * 30 +
            ["dismissed"]          * 20
        )

        selected_pairs = random.sample(PAIR_TEMPLATES, n_pairs)
        all_claims     = []

        for tpl in selected_pairs:
            outcome   = pick(outcomes)
            u_lost    = pick(users)
            u_found   = pick([u for u in users if u.pk != u_lost.pk])

            # Dates — found is same day or within 3 days of lost
            days_ago   = random.randint(5, 90)
            lost_date  = (timezone.now() - timedelta(days=days_ago)).date()
            found_date = lost_date + timedelta(days=random.randint(0, 3))
            report_dt  = rdatetime(days_back_min=days_ago, days_back_max=days_ago + 1)
            found_dt   = report_dt + timedelta(hours=random.randint(2, 72))

            # Resolve descriptions — SAME item_name, real names injected
            item_name  = tpl["item_name"]
            lost_desc  = fill(tpl["lost_desc"],  owner=u_lost,  finder=u_found)
            found_desc = fill(tpl["found_desc"], owner=u_lost,  finder=u_found)
            proof_desc = fill(tpl.get("proof_desc", ""), owner=u_lost, finder=u_found)
            feature    = fill(tpl.get("feature", ""),   owner=u_lost, finder=u_found)

            # Statuses
            if outcome == "confirmed_matched":
                ls, fs, ms_s = "matched",     "matched",     "confirmed"
            elif outcome == "confirmed_claimed":
                ls, fs, ms_s = "claimed",     "claimed",     "confirmed"
            elif outcome == "confirmed_closed":
                ls, fs, ms_s = "closed",      "closed",      "confirmed"
            elif outcome == "pending_suggestion":
                ls, fs, ms_s = "under_review","under_review","pending"
            else:
                ls, fs, ms_s = "open",        "open",        "dismissed"

            lost_r = LostReport.objects.create(
                user=u_lost,   report_type="lost",
                item_name=item_name,
                category=tpl["category"],
                location=tpl["location"],
                location_detail=maybe(pick(["Near the entrance","2nd floor","Ground floor","Near the vending machine"]), 0.4),
                date_event=lost_date, time_event=maybe(rtime_val(), 0.65),
                brand=tpl.get("brand"), color=tpl.get("color"),
                description=lost_desc,
                distinguishing_features=feature or None,
                reward=tpl.get("reward"),
                contact_phone=maybe(rphone(), 0.6),
                is_urgent=(tpl.get("reward") is not None or random.random() < 0.12),
                status=ls,
                admin_notes="Match confirmed. Please coordinate pickup with the finder." if ls in ("matched","claimed","closed") else None,
                views=random.randint(10, 200),
                date_reported=report_dt,
            )
            LostReport.objects.filter(pk=lost_r.pk).update(date_reported=report_dt)

            found_r = LostReport.objects.create(
                user=u_found,  report_type="found",
                item_name=item_name,
                category=tpl["category"],
                location=tpl["location"],
                location_detail=maybe(pick(["Near the exit","Near the notice board","On a bench"]), 0.35),
                date_event=found_date, time_event=maybe(rtime_val(), 0.55),
                brand=tpl.get("brand"), color=tpl.get("color"),
                description=found_desc,
                distinguishing_features=feature or None,
                found_stored_at=pick(FOUND_STORED_AT),
                is_urgent=False, status=fs,
                admin_notes="Finder has been contacted. Item is secured." if fs in ("matched","claimed","closed") else None,
                views=random.randint(5, 130),
                date_reported=found_dt,
            )
            LostReport.objects.filter(pk=found_r.pk).update(date_reported=found_dt)

            # Link matched_report FK for confirmed outcomes
            if ms_s == "confirmed":
                LostReport.objects.filter(pk=lost_r.pk).update(matched_report=found_r)
                LostReport.objects.filter(pk=found_r.pk).update(matched_report=lost_r)

            # Match suggestion
            score      = round(random.uniform(0.75, 0.98) if ms_s == "confirmed"
                               else random.uniform(0.22, 0.72), 3)
            confidence = "high" if score >= 0.75 else ("medium" if score >= 0.50 else "low")
            MatchSuggestion.objects.create(
                lost_report=lost_r, found_report=found_r,
                score=score, confidence=confidence,
                score_breakdown={
                    "category":    round(random.uniform(0.25, 0.35), 3),
                    "name":        round(random.uniform(0.20, 0.30), 3),
                    "location":    round(random.uniform(0.08, 0.18), 3),
                    "date":        round(random.uniform(0.05, 0.12), 3),
                    "description": round(random.uniform(0.05, 0.15), 3),
                },
                status=ms_s,
            )

            # Claim for claimed/closed outcomes
            if outcome in ("confirmed_claimed", "confirmed_closed"):
                cl = ClaimRequest.objects.create(
                    report=found_r, claimant=u_lost,
                    proof_description=proof_desc or f"I can identify the unique features: {feature}.",
                    status="approved",
                    admin_response=pick([
                        "Ownership verified. Claimant matched all item details.",
                        "Confirmed — claimant knew details only the true owner would know.",
                        "Approved. Unique identifiers verified in person.",
                    ]),
                )
                all_claims.append(cl)

        n_pairs_done = len(selected_pairs)
        self.stdout.write(self.style.SUCCESS(
            f"  ✓ {n_pairs_done} pairs → {n_pairs_done*2} reports, "
            f"{MatchSuggestion.objects.count()} suggestions, {len(all_claims)} claims"))

        # ── 4. FALSE POSITIVE SUGGESTIONS ───────────────────────────────────────
        self.stdout.write("Creating false positive suggestions…")
        existing_pairs = set(MatchSuggestion.objects.values_list("lost_report_id","found_report_id"))
        lost_list  = list(LostReport.objects.filter(report_type="lost"))
        found_list = list(LostReport.objects.filter(report_type="found"))
        random.shuffle(lost_list); random.shuffle(found_list)
        fp = 0
        for lr in lost_list[:20]:
            for fr in found_list:
                if fp >= 20: break
                if (lr.pk, fr.pk) in existing_pairs: continue
                if lr.category != fr.category:       continue
                if lr.item_name == fr.item_name:     continue  # don't fake-match same item
                score = round(random.uniform(0.12, 0.52), 3)
                MatchSuggestion.objects.create(
                    lost_report=lr, found_report=fr, score=score,
                    confidence="medium" if score >= 0.50 else "low",
                    score_breakdown={
                        "category": round(random.uniform(0.10, 0.22), 3),
                        "name":     round(random.uniform(0.02, 0.12), 3),
                        "location": round(random.uniform(0.00, 0.08), 3),
                        "date":     round(random.uniform(0.00, 0.06), 3),
                    },
                    status=pick(["pending","dismissed","dismissed"]),
                )
                existing_pairs.add((lr.pk, fr.pk))
                fp += 1
        self.stdout.write(self.style.SUCCESS(f"  ✓ {fp} false positive suggestions"))

        # ── 5. SOLO REPORTS ─────────────────────────────────────────────────────
        self.stdout.write(f"Creating {n_solo} solo reports…")
        solo_sp = ["open"]*45 + ["under_review"]*25 + ["rejected"]*15 + ["closed"]*15
        selected_solo = random.sample(SOLO_TEMPLATES, n_solo)

        for s in selected_solo:
            u      = pick(users)
            status = pick(solo_sp)
            dt     = rdatetime(days_back_max=150)
            desc   = fill(s["desc"], owner=u, finder=u)

            kwargs = dict(
                user=u, report_type=s["rt"],
                item_name=s["item"], category=s["cat"],
                location=s["loc"], location_detail=s.get("detail"),
                date_event=rdate(150), time_event=maybe(rtime_val(), 0.5),
                brand=s.get("brand"), color=s.get("color"),
                description=desc, is_urgent=random.random() < 0.1,
                status=status, views=random.randint(0, 100),
                date_reported=dt,
            )
            if s["rt"] == "lost":
                kwargs["reward"]        = s.get("reward")
                kwargs["contact_phone"] = maybe(rphone(), 0.45)
            else:
                kwargs["found_stored_at"] = pick(FOUND_STORED_AT)

            if status in ("rejected", "closed"):
                kwargs["admin_notes"] = pick([
                    "Report closed. Item has been returned to the owner.",
                    "Rejected — duplicate submission. See the existing report.",
                    "Closed by admin after 30 days with no activity.",
                    "Item claimed and returned successfully. Case closed.",
                    "Rejected — insufficient information provided.",
                ])

            r = LostReport.objects.create(**kwargs)
            LostReport.objects.filter(pk=r.pk).update(date_reported=dt)

        self.stdout.write(self.style.SUCCESS(f"  ✓ {n_solo} solo reports"))

        # ── 6. NOTIFICATIONS ────────────────────────────────────────────────────
        self.stdout.write("Creating notifications…")

        def notif(user, ntype, title, msg, report=None, claim=None):
            Notification.objects.create(
                user=user, notif_type=ntype, title=title, message=msg,
                report=report, claim=claim, is_read=random.random() < 0.55)

        for r in LostReport.objects.select_related("user").all():
            notif(r.user, "report_received", "Report Received",
                  f"Your {r.report_type} report for '{r.item_name}' has been received.", report=r)
            notif(admin, "new_report", "New Report Submitted",
                  f"New {r.report_type} report: '{r.item_name}' by @{r.user.username}.", report=r)
            if r.status in ("under_review","matched","claimed","closed"):
                notif(r.user, "under_review", "Report Under Review",
                      f"Your report for '{r.item_name}' is now under review by our team.", report=r)
            if r.status in ("matched","claimed","closed"):
                notif(r.user, "matched", "Match Found!",
                      f"A match was found for your '{r.item_name}' report!", report=r)

        for cl in all_claims:
            notif(cl.report.user, "claim_received", "New Claim Submitted",
                  f"A claim was submitted for '{cl.report.item_name}'.",
                  report=cl.report, claim=cl)
            notif(admin, "new_claim", "Claim Awaiting Review",
                  f"Claim for '{cl.report.item_name}' by @{cl.claimant.username}.",
                  report=cl.report, claim=cl)
            notif(cl.claimant, "claim_approved", "Claim Approved!",
                  f"Your claim for '{cl.report.item_name}' has been approved. Please coordinate pickup.",
                  report=cl.report, claim=cl)

        self.stdout.write(self.style.SUCCESS(f"  ✓ {Notification.objects.count()} notifications"))

        # ── 7. AUDIT LOGS ────────────────────────────────────────────────────────
        self.stdout.write("Creating audit logs…")

        def alog(action, actor, actor_type="user",
                 target_user=None, report=None, claim=None, detail=""):
            AuditLog.objects.create(
                action=action, actor=actor, actor_type=actor_type,
                target_user=target_user, report=report, claim=claim,
                detail=detail, ip=rip())

        for u in random.sample(users, min(35, len(users))):
            for action in random.choices(["login","logout","register"], k=random.randint(1, 4)):
                alog(action, u, detail=f"{action.capitalize()}: @{u.username}")

        all_reports_list = list(LostReport.objects.all())
        for r in random.sample(all_reports_list, min(80, len(all_reports_list))):
            alog("report_created", r.user, report=r,
                 detail=f"Created {r.report_type} report #{r.pk}: '{r.item_name}'")

        for ms in MatchSuggestion.objects.filter(status="confirmed"):
            alog("match_confirmed", admin, actor_type="admin", report=ms.lost_report,
                 detail=f"Match confirmed: Lost#{ms.lost_report_id} ↔ Found#{ms.found_report_id} (score: {ms.score:.2f})")

        for ms in MatchSuggestion.objects.filter(status="dismissed").order_by("?")[:10]:
            alog("match_dismissed", admin, actor_type="admin", report=ms.lost_report,
                 detail=f"Suggestion #{ms.pk} dismissed by admin")

        for cl in all_claims:
            alog("claim_submitted", cl.claimant, claim=cl, report=cl.report,
                 detail=f"Claim #{cl.pk} submitted by @{cl.claimant.username}")
            alog("claim_approved", admin, actor_type="admin", claim=cl, report=cl.report,
                 detail=f"Claim #{cl.pk} approved → '{cl.report.item_name}' returned")

        for u in [u for u in users if u.status == "banned"][:5]:
            alog("user_banned", admin, actor_type="admin", target_user=u,
                 detail=f"Admin banned @{u.username}")

        for u in random.sample(users, min(8, len(users))):
            alog("password_change", u, detail=f"@{u.username} changed their password")

        # ── SUMMARY ─────────────────────────────────────────────────────────────
        lc = LostReport.objects.filter(report_type="lost").count()
        fc = LostReport.objects.filter(report_type="found").count()
        ac = len([u for u in users if u.status == "active"])
        bc = len([u for u in users if u.status == "banned"])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("═" * 56))
        self.stdout.write(self.style.SUCCESS("  ✅  Seed complete!"))
        self.stdout.write(self.style.SUCCESS("═" * 56))
        self.stdout.write(f"  Users            : {User.objects.filter(is_superuser=False).count()} ({ac} active, {bc} banned)")
        self.stdout.write(f"  Reports          : {LostReport.objects.count()} ({lc} lost / {fc} found)")
        self.stdout.write(f"  Match Suggestions: {MatchSuggestion.objects.count()} ({MatchSuggestion.objects.filter(status='confirmed').count()} confirmed)")
        self.stdout.write(f"  Claims           : {ClaimRequest.objects.count()} ({ClaimRequest.objects.filter(status='approved').count()} approved)")
        self.stdout.write(f"  Notifications    : {Notification.objects.count()}")
        self.stdout.write(f"  Audit Logs       : {AuditLog.objects.count()}")
        self.stdout.write("")
        self.stdout.write("  Admin  : admin / admin123")
        self.stdout.write("  Users  : <any username> / password123")
        self.stdout.write("")