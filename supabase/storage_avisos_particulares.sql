-- Bucket de fotos de los avisos de particulares.
--
-- Va aparte de Alembic a propósito: es configuración de Supabase Storage, no
-- esquema de la base, y un downgrade no puede deshacer un bucket con objetos
-- dentro. Se ejecuta una vez en Supabase → SQL Editor, y es idempotente.
--
-- Las fotos del pipeline Python siguen en Cloudflare R2: los dos
-- almacenamientos conviven. Este bucket es solo para lo que suben los usuarios.

-- Público: las fotos se sirven por URL directa, sin firmar. El límite de 2 MB y
-- la lista de MIME los aplica Storage antes de escribir el objeto.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'avisos-particulares',
  'avisos-particulares',
  true,
  2097152,
  array['image/webp', 'image/jpeg', 'image/png']
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- Convención de ruta: <usuario_id>/<aviso_id>/<uuid>.webp
-- El primer segmento identifica al dueño, y es lo único que se compara: nadie
-- puede escribir, reemplazar ni borrar dentro de la carpeta de otro.
drop policy if exists fotos_particulares_insert on storage.objects;
create policy fotos_particulares_insert on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'avisos-particulares'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

drop policy if exists fotos_particulares_update on storage.objects;
create policy fotos_particulares_update on storage.objects
  for update to authenticated
  using (
    bucket_id = 'avisos-particulares'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  )
  with check (
    bucket_id = 'avisos-particulares'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

drop policy if exists fotos_particulares_delete on storage.objects;
create policy fotos_particulares_delete on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'avisos-particulares'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

-- Servir las fotos no necesita política —el bucket es público y va por el
-- endpoint público, fuera de RLS—, pero **borrar sí exige `select`**: la API de
-- Storage busca el objeto antes de eliminarlo, y sin esta política el borrado
-- responde OK y no borra nada, dejando archivos huérfanos para siempre.
drop policy if exists fotos_particulares_select on storage.objects;
create policy fotos_particulares_select on storage.objects
  for select to authenticated
  using (
    bucket_id = 'avisos-particulares'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );
