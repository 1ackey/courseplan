(function () {
  "use strict";

  var KEY_STORE = "courseplan-comment-key";
  var NAME_STORE = "courseplan-comment-name";

  function clientKey() {
    var key = localStorage.getItem(KEY_STORE);
    if (!key) {
      key = Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem(KEY_STORE, key);
    }
    return key;
  }

  function h(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function fmtDate(s) {
    return (s || "").slice(0, 10);
  }

  function postJSON(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(function (d) {
          return { status: r.status, data: d };
        });
      })
      .then(function (res) {
        if (res.status >= 400 || !res.data.ok) {
          throw new Error(res.data.error || "操作失败");
        }
        return res.data;
      });
  }

  function initRoot(root) {
    if (root.dataset.ready) return;
    root.dataset.ready = "1";

    var apiBase = root.dataset.api || "/notebook-admin/api/comments";
    var offering = root.dataset.offering;
    var listUrl = apiBase + "/" + offering + "?key=" + encodeURIComponent(clientKey());
    var status = h("span", "comments-status");

    root.textContent = "";

    var form = h("form", "comments-form");
    var nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "昵称（可不填）";
    nameInput.maxLength = 40;
    nameInput.value = localStorage.getItem(NAME_STORE) || "";
    var bodyInput = document.createElement("textarea");
    bodyInput.placeholder = "写点什么给这门课…（学习体验、考核特点、给学弟学妹的建议都可以）";
    bodyInput.required = true;
    bodyInput.maxLength = 1500;
    var submit = h("button", "comments-submit", "发布留言");
    submit.type = "submit";
    form.appendChild(nameInput);
    form.appendChild(bodyInput);
    form.appendChild(submit);
    form.appendChild(status);

    var list = h("div", "comments-list");
    root.appendChild(form);
    root.appendChild(list);

    function refresh() {
      fetch(listUrl)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          list.textContent = "";
          if (!data.ok) {
            status.textContent = data.error || "留言加载失败";
            return;
          }
          if (!data.comments.length) {
            list.appendChild(h("p", "comments-empty", "还没有留言，来抢个沙发吧～"));
            return;
          }
          data.comments.forEach(function (c) {
            list.appendChild(renderComment(c));
          });
        })
        .catch(function () {
          status.textContent = "留言加载失败，请稍后再试";
        });
    }

    function renderComment(c) {
      var wrap = h("div", "comment");
      var head = h("div", "comment-head");
      head.appendChild(h("strong", "comment-author", c.author));
      head.appendChild(
        h("span", "comment-date",
          fmtDate(c.updated_at || c.created_at) + (c.updated_at ? " · 已编辑" : ""))
      );
      var body = h("div", "comment-body", c.body);
      wrap.appendChild(head);
      wrap.appendChild(body);

      if (c.can_edit) {
        var actions = h("div", "comment-actions");
        var editBtn = h("button", "comment-link", "编辑");
        var delBtn = h("button", "comment-link", "删除");
        editBtn.type = "button";
        delBtn.type = "button";
        actions.appendChild(editBtn);
        actions.appendChild(delBtn);
        wrap.appendChild(actions);

        editBtn.addEventListener("click", function () {
          var ta = document.createElement("textarea");
          ta.className = "comment-edit-box";
          ta.value = c.body;
          var bar = h("div", "comment-actions");
          var save = h("button", "comment-link", "保存");
          var cancel = h("button", "comment-link", "取消");
          save.type = "button";
          cancel.type = "button";
          bar.appendChild(save);
          bar.appendChild(cancel);
          body.replaceWith(ta);
          actions.replaceWith(bar);

          save.addEventListener("click", function () {
            postJSON(apiBase + "/" + c.id + "/edit", {
              key: clientKey(),
              body: ta.value,
              author: nameInput.value.trim(),
            })
              .then(function () { refresh(); })
              .catch(function (err) { status.textContent = err.message; });
          });
          cancel.addEventListener("click", refresh);
        });

        delBtn.addEventListener("click", function () {
          if (!window.confirm("确定删除这条留言吗？")) return;
          postJSON(apiBase + "/" + c.id + "/delete", { key: clientKey() })
            .then(function () { refresh(); })
            .catch(function (err) { status.textContent = err.message; });
        });
      }
      return wrap;
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var body = bodyInput.value.trim();
      if (!body) return;
      status.textContent = "发布中…";
      postJSON(apiBase + "/" + offering, {
        body: body,
        author: nameInput.value.trim(),
        key: clientKey(),
      })
        .then(function () {
          localStorage.setItem(NAME_STORE, nameInput.value.trim());
          bodyInput.value = "";
          status.textContent = "已发布 ✓";
          refresh();
        })
        .catch(function (err) {
          status.textContent = err.message || "发布失败";
        });
    });

    refresh();
  }

  function init() {
    var roots = document.querySelectorAll(".course-comments");
    for (var i = 0; i < roots.length; i++) initRoot(roots[i]);
  }

  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
