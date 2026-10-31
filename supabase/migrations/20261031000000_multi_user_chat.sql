create extension if not exists vector with schema extensions;

create table if not exists public.chats (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null default 'New Conversation',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, owner_id)
);
create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  chat_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('user','assistant')),
  content text not null,
  sources jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  foreign key (chat_id, owner_id) references public.chats(id, owner_id) on delete cascade
);
create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  chat_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  original_filename text not null,
  storage_path text not null unique,
  size_bytes bigint not null,
  content_hash text not null,
  chunk_count integer not null default 0,
  created_at timestamptz not null default now(),
  foreign key (chat_id, owner_id) references public.chats(id, owner_id) on delete cascade,
  unique (chat_id, content_hash)
);
create table if not exists public.document_chunks (
  id bigint generated always as identity primary key,
  chat_id uuid not null,
  document_id uuid not null references public.documents(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  filename text not null,
  chunk_index integer not null,
  content text not null,
  embedding extensions.vector(768) not null,
  foreign key (chat_id, owner_id) references public.chats(id, owner_id) on delete cascade
);
create index if not exists document_chunks_embedding_idx on public.document_chunks
  using ivfflat (embedding extensions.vector_cosine_ops) with (lists = 100);
create index if not exists chats_owner_updated_idx on public.chats(owner_id, updated_at desc);
create index if not exists messages_owner_chat_idx on public.messages(owner_id, chat_id, created_at);
create index if not exists docs_owner_chat_idx on public.documents(owner_id, chat_id);

create or replace function public.touch_chat_updated_at() returns trigger
language plpgsql as $$ begin new.updated_at = now(); return new; end $$;
drop trigger if exists chats_touch_updated_at on public.chats;
create trigger chats_touch_updated_at before update on public.chats
for each row execute function public.touch_chat_updated_at();

alter table public.chats enable row level security;
alter table public.messages enable row level security;
alter table public.documents enable row level security;
alter table public.document_chunks enable row level security;
do $$ declare t text; begin
  foreach t in array array['chats','messages','documents','document_chunks'] loop
    execute format('drop policy if exists owner_all on public.%I', t);
    execute format('create policy owner_all on public.%I for all using (owner_id = auth.uid()) with check (owner_id = auth.uid())', t);
  end loop;
end $$;
grant select, insert, update, delete on public.chats, public.messages,
  public.documents, public.document_chunks to authenticated, service_role;
grant usage, select on all sequences in schema public to authenticated, service_role;

create or replace function public.match_document_chunks(
  query_embedding extensions.vector(768), match_owner_id uuid,
  match_chat_id uuid, match_count int
) returns table(document_id uuid, filename text, chunk_index int, content text, similarity float)
language sql stable security definer set search_path = public, extensions as $$
  select c.document_id, c.filename, c.chunk_index, c.content,
         1 - (c.embedding <=> query_embedding) as similarity
  from public.document_chunks c
  where c.owner_id = match_owner_id and c.chat_id = match_chat_id
  order by c.embedding <=> query_embedding limit match_count;
$$;
revoke all on function public.match_document_chunks(extensions.vector, uuid, uuid, int) from public, anon, authenticated;
grant execute on function public.match_document_chunks(extensions.vector, uuid, uuid, int) to service_role;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('user-documents', 'user-documents', false, 10485760,
        array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','text/plain'])
on conflict (id) do nothing;
drop policy if exists user_document_owner_all on storage.objects;
create policy user_document_owner_all on storage.objects for all
using (bucket_id = 'user-documents' and (storage.foldername(name))[1] = auth.uid()::text)
with check (bucket_id = 'user-documents' and (storage.foldername(name))[1] = auth.uid()::text);
