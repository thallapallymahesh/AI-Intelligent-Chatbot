alter table public.chats add column if not exists archived boolean not null default false;
alter table public.messages add column if not exists feedback smallint
  check (feedback is null or feedback in (-1, 1));
alter table public.document_chunks add column if not exists page_number integer;
create index if not exists chats_owner_archived_updated_idx
  on public.chats(owner_id, archived, updated_at desc);

drop function if exists public.match_document_chunks(extensions.vector, uuid, uuid, int);
create function public.match_document_chunks(
  query_embedding extensions.vector(768), match_owner_id uuid,
  match_chat_id uuid, match_count int
) returns table(document_id uuid, filename text, chunk_index int,
                content text, page_number int, similarity float)
language sql stable security definer set search_path = public, extensions as $$
  select c.document_id, c.filename, c.chunk_index, c.content, c.page_number,
         1 - (c.embedding <=> query_embedding) as similarity
  from public.document_chunks c
  where c.owner_id = match_owner_id and c.chat_id = match_chat_id
  order by c.embedding <=> query_embedding limit match_count;
$$;
revoke all on function public.match_document_chunks(extensions.vector, uuid, uuid, int)
  from public, anon, authenticated;
grant execute on function public.match_document_chunks(extensions.vector, uuid, uuid, int)
  to service_role;
