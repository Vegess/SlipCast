import { Component, computed, input } from '@angular/core';

interface Block { type: 'h' | 'p' | 'ul'; level?: number; html?: string; items?: string[]; }

/** Escapes HTML first, then applies **bold** only, so model output can never inject markup. */
function inline(text: string): string {
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  return escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

/** Minimal Markdown (headings, bullet lists, paragraphs) for status reports. */
@Component({
  selector: 'app-markdown',
  template: `
    <div class="space-y-3 text-sm leading-relaxed">
      @for (b of blocks(); track $index) {
        @switch (b.type) {
          @case ('h') { <p [class]="b.level === 1 ? 'font-display text-lg font-medium' : 'font-medium text-fg'" [innerHTML]="b.html"></p> }
          @case ('ul') { <ul class="list-disc space-y-1 pl-5 text-fg/85">@for (i of b.items; track $index) { <li [innerHTML]="i"></li> }</ul> }
          @default { <p class="text-fg/85" [innerHTML]="b.html"></p> }
        }
      }
    </div>`,
})
export class MarkdownComponent {
  readonly source = input.required<string>();
  readonly blocks = computed<Block[]>(() => {
    const out: Block[] = [];
    for (const raw of this.source().split('\n')) {
      const line = raw.trim();
      if (!line) continue;
      const h = /^(#{1,4})\s+(.*)$/.exec(line);
      const li = /^[-*]\s+(.*)$/.exec(line);
      if (h) out.push({ type: 'h', level: h[1].length, html: inline(h[2]) });
      else if (li) {
        const last = out[out.length - 1];
        if (last?.type === 'ul') last.items!.push(inline(li[1]));
        else out.push({ type: 'ul', items: [inline(li[1])] });
      } else out.push({ type: 'p', html: inline(line) });
    }
    return out;
  });
}
