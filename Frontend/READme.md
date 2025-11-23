In this frontend uses Supabase as the database and for some fucntions like email verification in order to verify/authenticate your existence of the email as the owner or the person in the facility.

How to run

Change Directory into "Frontend" folder

`cd Frontend`

Then install all packages

`npm install`

Setup .env files from your Supabase (Note that these configs can be accessed in Supabase menu on the left hand side and press on `Project Settings`)

Pre-set default names that are set in the .env are these listed below:

VITE_SUPABASE_URL=YOUR_SUPABASE_PROJECT_URL // Replace the Supabase project URL after the equal sign "=" 

VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY // and replace your API from API Key button in the supabase config. *Latest update of supabase UI have `API key & Legacy API keys`, access this directly from the `Legacy API Keys` for anon_keys

*For easier copy & paste here*

VITE_SUPABASE_URL=YOUR_SUPABASE_PROJECT_URL
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY

After you have set up the .env file in the Frontend folder and have replaced everything
Run the dev server by

`npm run dev` or others like

`npm run build` for production

`npm run preview` for view build production locally.

