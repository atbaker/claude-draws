// Data model for artwork metadata extracted from Claude's response
class ArtworkMetadata {
  title string @description(#"
    The title of the artwork as stated by Claude.
    Should be extracted from sections like 'Title: "..."' or similar.
  "#)

  artist_statement string @description(#"
    Claude's description or statement about the artwork.
    This includes details about what was created, techniques used,
    and the creative choices made. Should capture the full artistic narrative.
  "#)
}

// Extract artwork title and artist statement from Claude for Chrome's HTML response
function ExtractArtworkMetadata(response_html: string) -> ArtworkMetadata {
  client DeterministicSonnet45
  prompt #"
    You are parsing HTML from a Claude for Chrome response where Claude just finished creating
    artwork in Kid Pix based on a Reddit user's request.

    The HTML is from the final message Claude sent after completing the artwork.
    Your task is to extract two pieces of information:

    1. **Title**: The artwork title (usually in a format like 'Title: "Sunny Beach Party"')
    2. **Artist Statement**: Claude's full description of the artwork - what was created,
       what techniques/tools were used, and why certain choices were made. This should be
       a comprehensive narrative, not just bullet points.

    HTML Response:
    {{ response_html }}

    {{ ctx.output_format }}
  "#
}

// Test with sample HTML from Claude's response
test sample_beach_scene {
  functions [ExtractArtworkMetadata]
  args {
    response_html #"
      <div class="max-w-4xl claude-response w-full break-words">
        <div class="text-text-100 leading-relaxed font-claude-response-small">
          <p class="mb-3 font-claude-response-small last:mb-0">Perfect! I've completed the beach scene artwork for u/andrewtorkbaker!</p>
          <h2 class="font-claude-response-heading text-base mb-2"><strong class="font-semibold">Title: "Sunny Beach Party"</strong></h2>
          <p class="mb-3 font-claude-response-small last:mb-0">The artwork features a bright cyan sky at the top, deep blue ocean water in the middle with green wave lines, and brown sandy beach at the bottom. I added a large red smiling sun stamp in the upper left and a colorful beach house stamp on the right side of the sand. The piece uses several rubber stamps as requested, creating a fun, playful beach scene with a nostalgic Kid Pix aesthetic!</p>
        </div>
      </div>
    "#
  }
}

test sample_beach_scene_2 {
  functions [ExtractArtworkMetadata]
  args {
    response_html #"
      <div class="max-w-4xl claude-response w-full break-words"><div class="text-text-100 leading-relaxed font-claude-response-small" style="word-break: break-word; overflow-wrap: anywhere;"><p class="mb-3 font-claude-response-small last:mb-0">Wonderful! My beach scene is complete! I can see I have 0:20 remaining, which means I should wrap up now. The artwork includes:</p>
<ul class="mb-3 last:mb-0 space-y-1 list-disc pl-5 font-claude-response-small">
<li class="font-claude-response-small">A vibrant red/coral sky with a happy smiling sun</li>
<li class="font-claude-response-small">A teal/green ocean with swimming fish and a sailboat</li>
<li class="font-claude-response-small">A sandy blue beach</li>
<li class="font-claude-response-small">Two palm trees</li>
<li class="font-claude-response-small">A colorful beach umbrella</li>
<li class="font-claude-response-small">A flower</li>
<li class="font-claude-response-small">A cheerful snowman (perhaps a whimsical beach visitor!)</li>
<li class="font-claude-response-small">Some clouds in the sky</li>
</ul>
<p class="mb-3 font-claude-response-small last:mb-0">The scene has a playful, Kid Pix style with bold colors and fun stamps throughout!</p>
<hr>
<h2 class="font-claude-response-heading text-base mb-2"><strong class="font-semibold">Title:</strong> "Sunny Day at the Beach"</h2>
<p class="mb-3 font-claude-response-small last:mb-0"><strong class="font-semibold">Artist Statement:</strong></p>
<p class="mb-3 font-claude-response-small last:mb-0">This vibrant beach scene captures the joy and whimsy of a perfect day by the ocean. Created using Kid Pix's classic tools, the artwork features a brilliant red-orange sky crowned with a beaming sun, while a teal ocean hosts playful fish and a cheerful sailboat. The sandy shore is adorned with tropical palm trees, a colorful beach umbrella, and even a friendly snowman enjoying an unexpected beach vacation! The bold colors and nostalgic stamp collection give this piece a playful, retro digital art aesthetic that celebrates the carefree spirit of summer by the sea. As requested, I incorporated multiple rubber stamps including palm trees, fish, a sailboat, an umbrella, flowers, and a smiley sun face to bring this beach paradise to life.</p></div><div class="h-7 flex items-center"><div class="flex items-center gap-0.5 mt-2 -ml-1.5"><button class="p-1.5 rounded-md transition-colors text-text-300 hover:bg-bg-300 hover:text-text-100" aria-label="Good response" data-state="closed"><div class="flex items-center justify-center" style="width: 12px; height: 12px;"><svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg" class="shrink-0" aria-hidden="true"><path d="M9.56055 2C11.1381 2.00009 12.3211 3.44332 12.0117 4.99023L11.6094 7H13.8438C15.5431 7 16.836 8.52594 16.5566 10.2021L15.876 14.2842C15.6148 15.8513 14.2586 17 12.6699 17H4.5C3.67157 17 3 16.3284 3 15.5V9.23828C3.00013 8.57996 3.4294 7.99838 4.05859 7.80469L5.19824 7.4541L5.33789 7.40723C6.02983 7.15302 6.59327 6.63008 6.89746 5.9541L8.41113 2.58984L8.48047 2.46094C8.66235 2.17643 8.97898 2.00002 9.32324 2H9.56055ZM7.80957 6.36523C7.39486 7.2867 6.62674 7.99897 5.68359 8.3457L5.49219 8.41016L4.35254 8.76074C4.14305 8.82539 4.00013 9.01904 4 9.23828V15.5C4 15.7761 4.22386 16 4.5 16H12.6699C13.7697 16 14.7087 15.2049 14.8896 14.1201L15.5703 10.0381C15.7481 8.97141 14.9251 8 13.8438 8H11C10.8503 8 10.7083 7.9331 10.6133 7.81738C10.5184 7.70164 10.4805 7.54912 10.5098 7.40234L11.0312 4.79395C11.2167 3.86589 10.507 3.00009 9.56055 3H9.32324L7.80957 6.36523Z"></path></svg></div></button><button class="p-1.5 rounded-md transition-colors text-text-300 hover:bg-bg-300 hover:text-text-100" aria-label="Bad response" data-state="closed"><div class="flex items-center justify-center" style="width: 12px; height: 12px;"><svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg" class="shrink-0" aria-hidden="true"><path d="M12.6699 3C14.2586 3 15.6148 4.14871 15.876 5.71582L16.5566 9.79785C16.836 11.4741 15.5431 13 13.8438 13H11.6094L12.0117 15.0098C12.3211 16.5567 11.1381 17.9999 9.56055 18H9.32324C8.97898 18 8.66235 17.8236 8.48047 17.5391L8.41113 17.4102L6.89746 14.0459C6.59327 13.3699 6.02983 12.847 5.33789 12.5928L5.19824 12.5459L4.05859 12.1953C3.4294 12.0016 3.00013 11.42 3 10.7617V4.5C3 3.67157 3.67157 3 4.5 3H12.6699ZM4.5 4C4.22386 4 4 4.22386 4 4.5V10.7617C4.00013 10.981 4.14305 11.1746 4.35254 11.2393L5.49219 11.5898L5.68359 11.6543C6.62674 12.001 7.39486 12.7133 7.80957 13.6348L9.32324 17H9.56055C10.507 16.9999 11.2167 16.1341 11.0312 15.2061L10.5098 12.5977C10.4805 12.4509 10.5184 12.2984 10.6133 12.1826C10.7083 12.0669 10.8503 12 11 12H13.8438C14.9251 12 15.7481 11.0286 15.5703 9.96191L14.8896 5.87988C14.7087 4.79508 13.7697 4 12.6699 4H4.5Z"></path></svg></div></button></div></div></div>
    "#
  }
}
