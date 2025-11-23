-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.Faculty Member (
  U_id uuid NOT NULL,
  role_id smallint NOT NULL,
  staff_id numeric NOT NULL,
  CONSTRAINT Faculty Member_pkey PRIMARY KEY (U_id),
  CONSTRAINT Faculty Member_U_id_fkey FOREIGN KEY (U_id) REFERENCES public.Users(id),
  CONSTRAINT Faculty Member_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.Role(r_id)
);
CREATE TABLE public.Role (
  r_id smallint GENERATED ALWAYS AS IDENTITY NOT NULL,
  RoleName character varying NOT NULL,
  CONSTRAINT Role_pkey PRIMARY KEY (r_id)
);
CREATE TABLE public.Student (
  u_id uuid NOT NULL,
  role_id smallint NOT NULL,
  StudentID numeric NOT NULL UNIQUE,
  CONSTRAINT Student_pkey PRIMARY KEY (u_id),
  CONSTRAINT Student_u_id_fkey FOREIGN KEY (u_id) REFERENCES public.Users(id),
  CONSTRAINT Student_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.Role(r_id)
);
CREATE TABLE public.Users (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  Name text NOT NULL UNIQUE,
  Email character varying NOT NULL UNIQUE,
  Role smallint NOT NULL,
  GrafanaID character varying NOT NULL,
  Proxmox character varying NOT NULL,
  CONSTRAINT Users_pkey PRIMARY KEY (id),
  CONSTRAINT Users1_Role_fkey FOREIGN KEY (Role) REFERENCES public.Role(r_id)
);