frappe.ui.form.on('Purchase Receipt', {
    refresh: function(frm) {
        // Add button for single document processing
        frm.add_custom_button(__('Process Single Document'), function() {
            uploadAndProcessDocument(frm, false);
        });

        // Add button for multiple document processing
        frm.add_custom_button(__('Process Multiple Documents'), function() {
            uploadAndProcessDocument(frm, true);
        });

        // Add button for generating multiple rows
        frm.add_custom_button(__('Generate Multiple Rows'), function() {
            showGenerateRowsDialog(frm);
        });
    }
});

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
        method: multiple ? 'ocr.api.api.process_multiple_documents' : 'ocr.api.api.extract_document_data',
        multiple: multiple,
        on_success: (file_doc) => {
            handleUploadSuccess(frm, file_doc, multiple);
        }
    });
}

function handleUploadSuccess(frm, file_doc, multiple) {
    // Show processing indicator
    frappe.show_alert({
        message: __('Processing document(s), please wait...'),
        indicator: 'blue'
    });

    // Prepare the method call
    const method = multiple ? 'ocr.api.api.process_multiple_documents' : 'ocr.api.api.extract_document_data';
    const args = multiple ? {
        docname: frm.doc.name,
        file_urls: file_doc.map(f => f.file_url)
    } : {
        docname: frm.doc.name,
        file_url: file_doc.file_url
    };

    // Make the API call
    frappe.call({
        method: method,
        args: args,
        callback: function(r) {
            handleProcessingResponse(frm, r, multiple);
        }
    });
}

function handleProcessingResponse(frm, r, multiple) {
    if (r.message.success) {
        const msg = multiple ? 
            `Successfully processed ${r.message.total_files} documents with ${r.message.total_rows} total rows` :
            `Successfully created ${r.message.rows_count} rows with data`;

        frappe.show_alert({
            message: __(msg),
            indicator: 'green'
        });

        // Reload the document to show updated data
        frm.reload_doc();
    } else {
        frappe.msgprint({
            title: __('Error'),
            indicator: 'red',
            message: __('Error: ' + r.message.error)
        });
    }
}

function showGenerateRowsDialog(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('Please add at least one item first.'));
        return;
    }

    let d = new frappe.ui.Dialog({
        title: 'Generate Multiple Rows',
        fields: [
            {
                label: 'Number of Rows',
                fieldname: 'num_rows',
                fieldtype: 'Int',
                reqd: 1,
                default: 1
            }
        ],
        primary_action_label: 'Generate',
        primary_action(values) {
            generateMultipleRows(frm, values.num_rows);
            d.hide();
        }
    });
    d.show();
}

function generateMultipleRows(frm, numRows) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('Please add at least one item first.'));
        return;
    }

    const templateRow = frm.doc.items[0];
    
    for (let i = 0; i < numRows; i++) {
        let row = frm.add_child('items', {
            'item_code': templateRow.item_code,
            'item_name': templateRow.item_name,
            'description': templateRow.description,
            'uom': templateRow.uom,
            'warehouse': templateRow.warehouse,
            'custom_attach_image': '',
            'custom_lot_no': '',
            'custom_reel_no': '',
            'qty': 0,
            'received_qty': 0,
            'accepted_qty': 0,
            'rejected_qty': 0
        });
    }
    
    frm.refresh_field('items');
    frappe.show_alert({
        message: __(`Generated ${numRows} new rows`),
        indicator: 'green'
    });
    
    frm.save()
        .then(() => {
            console.log(`Successfully generated ${numRows} rows`);
        })
        .catch(err => {
            console.error("Error saving document after generating rows:", err);
            frappe.msgprint(__('Error saving document after generating rows.'));
        });
}

// Row-level image processing
frappe.ui.form.on('Purchase Receipt Item', {
    custom_attach_image: async function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.custom_attach_image) {
            frappe.msgprint(__('Please upload an image.'));
            return;
        }

        try {
            await frm.save();
            
            frappe.call({
                method: 'ocr.api.api.extract_item_level_data',
                args: {
                    docname: frm.doc.name,
                    item_idx: row.idx
                },
                callback: function(r) {
                    if (r.message.success) {
                        frappe.show_alert({
                            message: __('Data extracted successfully!'),
                            indicator: 'green'
                        });
                        
                        frappe.model.set_value(cdt, cdn, {
                            'custom_lot_no': r.message.lot_no,
                            'custom_reel_no': r.message.reel_no,
                            'qty': r.message.qty,
                            'accepted_qty': r.message.qty,
                            'rejected_qty': 0
                        });
                        
                        frm.refresh_field("items");
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: __('Error: ' + r.message.error)
                        });
                    }
                }
            });
        } catch (error) {
            console.error("Error processing image:", error);
            frappe.msgprint(__('Error processing the image. Please try again.'));
        }
    }
});
