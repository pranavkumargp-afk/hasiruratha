
frappe.ready(function () {
  const wf = frappe.web_form;
  if (frappe.session && frappe.session.user && frappe.session.user !== "Guest") wf.set_value("email", frappe.session.user);
  const wrap = document.querySelector('.frappe-control[data-fieldname="verification_code"]');
  if (!wrap) return;
  wrap.insertAdjacentHTML("afterend", '<div style="margin:-6px 0 12px"><button type="button" class="btn btn-default btn-sm" id="hr-send-code">Send code to my email</button></div>');
  document.getElementById("hr-send-code").onclick = function () {
    frappe.call({ method: "hasiruratha.citizen_api.send_email_code", args: { email: wf.get_value("email") } })
      .then(() => frappe.msgprint(__("We sent a 6-digit code to your email. Enter it below.")));
  };
});
