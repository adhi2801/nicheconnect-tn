"""Tamil Nadu's places as brands write them (item 64, D-158).

Each group is one place: its usual English name first, then the other ways
people write it ("Kovai" for Coimbatore, "Trichy" for Tiruchirappalli). The
38 districts, by the name of the town each is run from, and a few large
towns that are not district seats. A creator's own city is typed freely, so
the reader also knows every city a findable creator wrote (`words_service`);
this list only adds the places nobody has typed yet and the other spellings.
"""

PLACES: tuple[tuple[str, ...], ...] = (
    ("Ariyalur",),
    ("Chengalpattu", "Chengalpet"),
    ("Chennai", "Madras"),
    ("Coimbatore", "Kovai"),
    ("Cuddalore",),
    ("Dharmapuri",),
    ("Dindigul",),
    ("Erode",),
    ("Kallakurichi",),
    ("Kanchipuram", "Kancheepuram", "Kanchi"),
    ("Nagercoil",),
    ("Kanyakumari", "Kanniyakumari"),
    ("Karur",),
    ("Krishnagiri",),
    ("Madurai",),
    ("Mayiladuthurai", "Mayuram"),
    ("Nagapattinam",),
    ("Namakkal",),
    ("Ooty", "Udhagamandalam", "Udagamandalam"),
    ("Perambalur",),
    ("Pudukkottai", "Pudukottai"),
    ("Ramanathapuram",),
    ("Ranipet",),
    ("Salem",),
    ("Sivaganga", "Sivagangai"),
    ("Tenkasi",),
    ("Thanjavur", "Tanjore"),
    ("Theni",),
    ("Thoothukudi", "Tuticorin"),
    ("Tiruchirappalli", "Trichy", "Tiruchi", "Tiruchy"),
    ("Tirunelveli", "Nellai", "Thirunelveli"),
    ("Tirupattur", "Tirupathur"),
    ("Tiruppur", "Tirupur"),
    ("Tiruvallur", "Thiruvallur"),
    ("Tiruvannamalai", "Thiruvannamalai"),
    ("Tiruvarur", "Thiruvarur"),
    ("Vellore",),
    ("Viluppuram", "Villupuram"),
    ("Virudhunagar",),
    ("Hosur",),
    ("Kumbakonam",),
    ("Karaikudi",),
    ("Pollachi",),
    ("Kodaikanal",),
    ("Rameswaram",),
    ("Puducherry", "Pondicherry", "Pondy"),
)
