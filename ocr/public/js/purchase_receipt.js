function uploadAndProcessDocument(frm, multiple) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('Please add at least one item first.'));
        return;
    }

    // Configure uploader
    const uploader = new frappe.ui.FileUploader({
        doctype: 'Purchase Receipt',
        docname: frm.doc.name,
        folder: 'Home/Attachments',
        allow_multiple: multiple,
        on_success: (file_doc) => {
            // For multiple files, file_doc will be an array
            const files = multiple ? file_doc : [file_doc];
            const file_urls = files.map(f => f.file_url);
            
            // Make the API call directly here instead of in a separate function
            frappe.call({
                method: multiple ? 'ocr.api.api.process_multiple_documents' : 'ocr.api.api.extract_document_data',
                args: {
                    docname: frm.doc.name,
                    file_urls: file_urls
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        const msg = multiple ? 
                            `Successfully processed ${r.message.total_files} documents with ${r.message.total_rows} total rows` :
                            `Successfully created ${r.message.rows_count} rows with data`;

                        frappe.show_alert({
                            message: __(msg),
                            indicator: 'green'
                        });

                        frm.reload_doc();
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: __('Error: ' + (r.message ? r.message.error : 'Unknown error'))
                        });
                    }
                }
            });
        }
    });

    uploader.show();
}
