"""Supabase project used for sign-in and recovery backup.
Both values are PUBLIC by design (the publishable key is safe to ship; Row Level Security protects the data).
Leave them empty to hide cloud features."""
SUPABASE_URL = "https://klwftooxmntwbsgmtacc.supabase.co"
SUPABASE_KEY = "sb_publishable_exFBEto-pCQ02wdxrCte_A_nRNGs9_Z"

GOOGLE_ENABLED = False  # set True only after enabling the Google provider in Supabase (needs a Google Cloud OAuth client)
