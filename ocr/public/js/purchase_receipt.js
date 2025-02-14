frappe.ui.form.on('Purchase Receipt', {
    refresh: function(frm) {
        // Add button for filling all rows from document
        frm.add_custom_button(__('Fill All Rows from Document'), function() {
            if (!frm.doc.items || frm.doc.items.length === 0) {
                frappe.msgprint(__('Please add at least one item first.'));
                return;
            }
            
            new frappe.ui.FileUploader({
                doctype: 'Purchase Receipt',
                docname: frm.doc.name,
                folder: 'Home/Attachments',
                on_success: (file_doc) => {
                    // Show a loading indicator
                    frappe.show_alert({
                        message: __('Processing document, please wait...'),
                        indicator: 'blue'
                    });
                    
                    frappe.call({
                        method: 'ocr.api.api.extract_document_data',
                        args: {
                            docname: frm.doc.name,
                            file_url: file_doc.file_url
                        },
                        callback: function(r) {
                            if (r.message.success) {
                                frappe.show_alert({
                                    message: __(`Successfully filled ${r.message.rows_count} rows with data`),
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
                    });
                }
            });
        });
        
        // Add button for generating multiple rows
        frm.add_custom_button(__('Generate Multiple Rows'), function() {
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
        });
    }
});

// Function to generate multiple rows
function generateMultipleRows(frm, numRows) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('Please add at least one item first.'));
        return;
    }

    // Get the first row as template
    const templateRow = frm.doc.items[0];
    
    // Create specified number of rows
    for (let i = 0; i < numRows; i++) {
        let row = frm.add_child('items', {
            'item_code': templateRow.item_code,
            'item_name': templateRow.item_name,
            'description': templateRow.description,
            'uom': templateRow.uom,
            'warehouse': templateRow.warehouse,
            // Clear the specific fields we want empty in new rows
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

frappe.ui.form.on('Purchase Receipt Item', {
    custom_attach_image: async function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.custom_attach_image) {
            frappe.msgprint(__('Please upload an image.'));
            console.log("No image uploaded. Exiting process.");
            return;
        }
        console.log("Image uploaded. Triggering form save...");
        try {
            await frm.save();
            console.log("Form saved successfully. Making API call...");
            
            frappe.call({
                method: 'ocr.api.api.extract_item_level_data',
                args: {
                    docname: frm.doc.name,
                    item_idx: row.idx
                },
                callback: function(r) {
                    if (r.message.success) {
                        frappe.msgprint(__('Data extracted successfully!'));
                        frappe.model.set_value(cdt, cdn, 'custom_lot_no', r.message.lot_no);
                        frappe.model.set_value(cdt, cdn, 'custom_reel_no', r.message.reel_no);
                        frappe.model.set_value(cdt, cdn, 'qty', r.message.qty);
                        frappe.model.set_value(cdt, cdn, 'accepted_qty', r.message.qty);
                        frappe.model.set_value(cdt, cdn, 'rejected_qty', 0);
                        console.log("Fields updated successfully.");
                        frm.refresh_field("items");
                        frm.reload_doc();
                    } else {
                        frappe.msgprint(__('Error: ' + r.message.error));
                    }
                }
            });
        } catch (error) {
            console.error("Error saving form or calling API:", error);
            frappe.msgprint(__('There was an error processing the extraction. Please try again.'));
        }
    }
});
