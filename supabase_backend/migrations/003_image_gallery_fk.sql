-- =============================================================================
-- Digidex — Add FK from image_gallery.image to image_urls.id
-- Run this in the Supabase SQL editor after 002_image_urls.sql
-- =============================================================================

ALTER TABLE image_gallery
    ADD CONSTRAINT fk_image_gallery_image
    FOREIGN KEY (image) REFERENCES image_urls(id)
    ON DELETE CASCADE;
