/**
 * SwitchInsights Comments + Reactions Widget
 * Uses Supabase REST API directly (no SDK dependency)
 */
(function () {
  'use strict';

  const SUPABASE_URL = 'https://jkiyisnoetcxndwtqoom.supabase.co';
  const SUPABASE_KEY = 'sb_publishable_UJOFqh8sPlZHAx56_hJXaw_N1onof2T';

  const HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': 'Bearer ' + SUPABASE_KEY,
    'Content-Type': 'application/json',
  };

  /* ── Helpers ────────────────────────────────────────────────────── */

  function getSlug() {
    const parts = window.location.pathname.split('/');
    const file = parts[parts.length - 1] || parts[parts.length - 2];
    return file.replace(/\.html$/, '') || 'index';
  }

  function relativeTime(iso) {
    const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function esc(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  /* ── Supabase REST ──────────────────────────────────────────────── */

  async function fetchComments(slug) {
    const url = SUPABASE_URL + '/rest/v1/comments?article_slug=eq.' +
      encodeURIComponent(slug) + '&approved=eq.true&select=*&order=created_at.asc';
    const r = await fetch(url, { headers: HEADERS });
    if (!r.ok) return [];
    return r.json();
  }

  async function fetchCommentCount(slug) {
    const url = SUPABASE_URL + '/rest/v1/comments?article_slug=eq.' +
      encodeURIComponent(slug) + '&approved=eq.true&select=id';
    const r = await fetch(url, { headers: { ...HEADERS, 'Prefer': 'count=exact' } });
    if (!r.ok) return 0;
    const count = r.headers.get('content-range');
    if (count) return parseInt(count.split('/')[1], 10) || 0;
    const data = await r.json();
    return data.length;
  }

  async function insertComment(payload) {
    const r = await fetch(SUPABASE_URL + '/rest/v1/comments', {
      method: 'POST',
      headers: { ...HEADERS, 'Prefer': 'return=minimal' },
      body: JSON.stringify(payload),
    });
    return r.ok;
  }

  async function fetchReactionCount(slug) {
    const url = SUPABASE_URL + '/rest/v1/reactions?article_slug=eq.' +
      encodeURIComponent(slug) + '&select=id';
    const r = await fetch(url, { headers: { ...HEADERS, 'Prefer': 'count=exact' } });
    if (!r.ok) return 0;
    const count = r.headers.get('content-range');
    if (count) return parseInt(count.split('/')[1], 10) || 0;
    const data = await r.json();
    return data.length;
  }

  async function insertReaction(slug) {
    const r = await fetch(SUPABASE_URL + '/rest/v1/reactions', {
      method: 'POST',
      headers: { ...HEADERS, 'Prefer': 'return=minimal' },
      body: JSON.stringify({ article_slug: slug }),
    });
    return r.ok;
  }

  /* ── CSS ────────────────────────────────────────────────────────── */

  function injectStyles() {
    if (document.getElementById('si-comments-css')) return;
    const css = `
      .si-reactions {
        display: flex; align-items: center; gap: 0.75rem;
        margin: 1rem 0 0.25rem; flex-wrap: wrap;
      }
      .si-reactions-btn {
        background: rgba(16,185,129,0.12); border: 1px solid rgba(16,185,129,0.35);
        color: #10B981; border-radius: 8px; padding: 0.35rem 0.85rem;
        font-size: 0.82rem; font-weight: 700; cursor: pointer;
        font-family: inherit; transition: background 0.15s, border-color 0.15s;
        display: inline-flex; align-items: center; gap: 0.35rem;
      }
      .si-reactions-btn:hover { background: rgba(16,185,129,0.22); border-color: rgba(16,185,129,0.6); }
      .si-reactions-btn.reacted { background: rgba(16,185,129,0.3); border-color: #10B981; }
      .si-reactions-count {
        font-size: 0.8rem; color: rgba(226,232,240,0.5); font-family: inherit;
      }
      .si-comment-count-badge {
        font-size: 0.8rem; color: rgba(226,232,240,0.5);
        font-family: inherit; font-style: normal;
      }

      .si-comments-section {
        max-width: 760px; margin: 3rem auto 0;
        padding: 2.5rem 1.5rem 3rem; border-top: 1px solid rgba(168,85,247,0.2);
      }
      .si-comments-heading {
        font-family: 'DM Serif Display', serif; font-size: 1.5rem;
        color: #fff; margin: 0 0 0.5rem;
      }
      .si-comments-subhead {
        font-size: 0.82rem; color: rgba(226,232,240,0.45); margin: 0 0 2rem;
      }

      /* Comment thread */
      .si-comment {
        border-left: 2px solid rgba(168,85,247,0.25);
        padding: 1rem 0 1rem 1.25rem; margin-bottom: 0.25rem;
      }
      .si-comment-reply { margin-left: 1.5rem; border-left-color: rgba(236,72,153,0.25); }
      .si-comment-meta {
        display: flex; align-items: baseline; gap: 0.6rem; margin-bottom: 0.45rem;
      }
      .si-comment-author { font-weight: 700; font-size: 0.9rem; color: #E2E8F0; }
      .si-comment-time { font-size: 0.75rem; color: rgba(226,232,240,0.4); }
      .si-comment-text {
        font-size: 0.92rem; color: rgba(226,232,240,0.85);
        line-height: 1.65; margin: 0 0 0.6rem; white-space: pre-wrap;
      }
      .si-reply-link {
        font-size: 0.78rem; color: rgba(168,85,247,0.7); cursor: pointer;
        background: none; border: none; padding: 0; font-family: inherit;
        text-decoration: none; transition: color 0.15s;
      }
      .si-reply-link:hover { color: #A855F7; }

      .si-no-comments {
        color: rgba(226,232,240,0.4); font-size: 0.9rem;
        font-style: italic; margin-bottom: 2rem;
      }

      /* Form */
      .si-comment-form {
        background: rgba(30,41,59,0.6); border: 1px solid rgba(168,85,247,0.2);
        border-radius: 14px; padding: 1.5rem; margin-top: 2rem;
      }
      .si-comment-form.si-reply-form {
        margin-top: 0.75rem; margin-left: 1.5rem;
        background: rgba(30,41,59,0.4); border-color: rgba(236,72,153,0.2);
      }
      .si-form-title {
        font-size: 0.8rem; font-weight: 700; letter-spacing: 0.08em;
        text-transform: uppercase; color: #A855F7; margin: 0 0 1rem;
      }
      .si-form-row { margin-bottom: 0.85rem; }
      .si-form-row input, .si-form-row textarea {
        width: 100%; background: rgba(15,23,42,0.7);
        border: 1px solid rgba(168,85,247,0.25); border-radius: 8px;
        color: #E2E8F0; font-family: inherit; font-size: 0.9rem;
        padding: 0.65rem 0.9rem; outline: none;
        transition: border-color 0.15s;
        resize: vertical;
      }
      .si-form-row input:focus, .si-form-row textarea:focus {
        border-color: rgba(168,85,247,0.6);
      }
      .si-form-row textarea { min-height: 90px; }
      .si-honeypot { display: none !important; }
      .si-form-actions { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
      .si-submit-btn {
        background: linear-gradient(135deg, #A855F7, #EC4899);
        color: #fff; border: none; border-radius: 8px;
        padding: 0.6rem 1.4rem; font-weight: 700; font-size: 0.88rem;
        cursor: pointer; font-family: inherit; transition: opacity 0.15s;
      }
      .si-submit-btn:hover { opacity: 0.88; }
      .si-submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .si-cancel-btn {
        background: none; border: none; color: rgba(226,232,240,0.4);
        font-size: 0.82rem; cursor: pointer; font-family: inherit;
        padding: 0; transition: color 0.15s;
      }
      .si-cancel-btn:hover { color: rgba(226,232,240,0.7); }
      .si-form-msg {
        font-size: 0.82rem; margin-top: 0.75rem; padding: 0.6rem 0.9rem;
        border-radius: 8px; display: none;
      }
      .si-form-msg.success {
        background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.35);
        color: #10B981; display: block;
      }
      .si-form-msg.error {
        background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.35);
        color: #F87171; display: block;
      }

      @media (max-width: 600px) {
        .si-comments-section { padding: 2rem 1rem 2.5rem; }
        .si-comment-form { padding: 1.1rem; }
        .si-comment-reply, .si-comment-form.si-reply-form { margin-left: 0.75rem; }
      }
    `;
    const style = document.createElement('style');
    style.id = 'si-comments-css';
    style.textContent = css;
    document.head.appendChild(style);
  }

  /* ── Render helpers ─────────────────────────────────────────────── */

  function buildFormHTML(parentId, cancelable) {
    return `
      <div class="${parentId ? 'si-comment-form si-reply-form' : 'si-comment-form'}"
           data-parent="${parentId || ''}">
        <div class="si-form-title">${parentId ? 'Write a reply' : 'Join the discussion'}</div>
        <div class="si-form-row">
          <input type="text" class="si-input-name" placeholder="Your name" maxlength="80" autocomplete="name" />
        </div>
        <div class="si-form-row">
          <textarea class="si-input-comment" placeholder="Share your thoughts..." maxlength="2000"></textarea>
        </div>
        <div class="si-honeypot si-form-row" aria-hidden="true">
          <input type="text" class="si-input-hp" tabindex="-1" autocomplete="off" />
        </div>
        <div class="si-form-actions">
          <button class="si-submit-btn" type="button">Post comment</button>
          ${cancelable ? '<button class="si-cancel-btn" type="button">Cancel</button>' : ''}
        </div>
        <div class="si-form-msg"></div>
      </div>`;
  }

  function renderComment(c, isReply) {
    return `
      <div class="si-comment ${isReply ? 'si-comment-reply' : ''}" data-id="${c.id}">
        <div class="si-comment-meta">
          <span class="si-comment-author">${esc(c.author_name)}</span>
          <span class="si-comment-time">${relativeTime(c.created_at)}</span>
        </div>
        <p class="si-comment-text">${esc(c.comment_text)}</p>
        ${!isReply ? `<button class="si-reply-link" data-cid="${c.id}">↩ Reply</button>` : ''}
      </div>`;
  }

  function renderThread(comments) {
    const topLevel = comments.filter(c => !c.parent_id);
    const replies = comments.filter(c => c.parent_id);
    if (!topLevel.length) return '';
    return topLevel.map(c => {
      const childReplies = replies.filter(r => r.parent_id === c.id);
      return renderComment(c, false) +
        childReplies.map(r => renderComment(r, true)).join('');
    }).join('');
  }

  /* ── Init ───────────────────────────────────────────────────────── */

  async function init() {
    injectStyles();
    const slug = getSlug();

    /* -- Reactions + comment count badge near byline -- */
    const byline = document.querySelector('.si-byline');
    if (byline) {
      const countBadge = document.createElement('span');
      countBadge.className = 'si-comment-count-badge';
      countBadge.textContent = '';
      byline.parentNode.insertBefore(countBadge, byline.nextSibling);

      const reactWrap = document.createElement('div');
      reactWrap.className = 'si-reactions';
      byline.parentNode.insertBefore(reactWrap, countBadge.nextSibling);

      const reacted = localStorage.getItem('si_reacted_' + slug) === '1';
      let reactionCount = 0;

      const renderReactions = (count, hasReacted) => {
        reactWrap.innerHTML = `
          <button class="si-reactions-btn${hasReacted ? ' reacted' : ''}" id="si-react-btn">
            👍 ${hasReacted ? 'Useful!' : 'Was this useful?'}
          </button>
          ${count > 0 ? `<span class="si-reactions-count">${count} ${count === 1 ? 'person' : 'people'} found this useful</span>` : ''}
        `;
        document.getElementById('si-react-btn').addEventListener('click', async () => {
          if (localStorage.getItem('si_reacted_' + slug) === '1') return;
          localStorage.setItem('si_reacted_' + slug, '1');
          await insertReaction(slug);
          reactionCount++;
          renderReactions(reactionCount, true);
        });
      };

      fetchReactionCount(slug).then(count => {
        reactionCount = count;
        renderReactions(count, reacted);
      });

      fetchCommentCount(slug).then(count => {
        countBadge.textContent = count > 0
          ? '💬 ' + count + (count === 1 ? ' comment' : ' comments')
          : '';
      });
    }

    /* -- Comments section -- */
    const footer = document.querySelector('footer.site-footer');
    if (!footer) return;

    const section = document.createElement('div');
    section.className = 'si-comments-section';
    section.innerHTML = `
      <h2 class="si-comments-heading">Discussion</h2>
      <p class="si-comments-subhead">Comments are moderated and appear once reviewed.</p>
      <div id="si-thread"></div>
      ${buildFormHTML(null, false)}
    `;
    footer.parentNode.insertBefore(section, footer);

    /* Load and render comments */
    const thread = document.getElementById('si-thread');
    const comments = await fetchComments(slug);

    if (!comments.length) {
      thread.innerHTML = '<p class="si-no-comments">No comments yet - be the first to start the discussion.</p>';
    } else {
      thread.innerHTML = renderThread(comments);
    }

    /* -- Event delegation for reply links and form submits -- */
    section.addEventListener('click', e => {
      /* Reply link */
      if (e.target.matches('.si-reply-link')) {
        const cid = e.target.dataset.cid;
        const existing = document.getElementById('si-reply-' + cid);
        if (existing) { existing.remove(); return; }
        const formWrap = document.createElement('div');
        formWrap.id = 'si-reply-' + cid;
        formWrap.innerHTML = buildFormHTML(cid, true);
        e.target.closest('.si-comment').insertAdjacentElement('afterend', formWrap);
        formWrap.querySelector('.si-cancel-btn').addEventListener('click', () => formWrap.remove());
        bindSubmit(formWrap.querySelector('.si-comment-form'), slug);
      }
    });

    bindSubmit(section.querySelector('.si-comment-form'), slug);
  }

  function bindSubmit(form, slug) {
    if (!form) return;
    const btn = form.querySelector('.si-submit-btn');
    const msg = form.querySelector('.si-form-msg');

    btn.addEventListener('click', async () => {
      const name = form.querySelector('.si-input-name').value.trim();
      const text = form.querySelector('.si-input-comment').value.trim();
      const hp = form.querySelector('.si-input-hp').value;
      const parentId = form.dataset.parent || null;

      msg.className = 'si-form-msg';
      msg.textContent = '';

      if (hp) return; /* honeypot triggered - silently discard */
      if (!name || name.length < 2) {
        msg.className = 'si-form-msg error';
        msg.textContent = 'Please enter your name.';
        return;
      }
      if (!text || text.length < 3) {
        msg.className = 'si-form-msg error';
        msg.textContent = 'Comment must be at least 3 characters.';
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Posting...';

      const ok = await insertComment({
        article_slug: slug,
        author_name: name,
        comment_text: text,
        parent_id: parentId || null,
      });

      if (ok) {
        form.querySelector('.si-input-name').value = '';
        form.querySelector('.si-input-comment').value = '';
        msg.className = 'si-form-msg success';
        msg.textContent = "Thanks! Your comment will appear once reviewed.";
        btn.textContent = 'Post comment';
        btn.disabled = false;
      } else {
        msg.className = 'si-form-msg error';
        msg.textContent = 'Something went wrong. Please try again.';
        btn.textContent = 'Post comment';
        btn.disabled = false;
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
